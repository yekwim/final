# simple_switch_final.py
#
# Controlador SDN (Ryu / OpenFlow 1.3) baseado em learning-switch,
# com suporte aos Experimentos 4 e 5:
#
#   - Exp. 4 (ECMP-sim): alterna dinamicamente entre s2 e s3
#   - Exp. 5 (Falha de link): se link s1-s2 cair, redireciona para rota via s3
#
# Requisito: manter as saídas do QUIC-sim (cliente/servidor) inalteradas.

from __future__ import annotations

import os
import random
from typing import Dict, Optional, Tuple

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4
from ryu.lib.packet import udp
from ryu.lib.packet import ether_types


# -----------------------------
# Configuração de Experimentos
# -----------------------------
EXPERIMENT = int(os.environ.get("EXPERIMENT", "4"))

# QUIC-sim usa UDP/4433
QUIC_UDP_PORT = 4433

# MACs padrão quando Mininet é executado com "--mac"
H1_MAC = os.environ.get("H1_MAC", "00:00:00:00:00:01")
H2_MAC = os.environ.get("H2_MAC", "00:00:00:00:00:02")

# -----------------------------
# Mapeamento de portas (DEFAULT)
# -----------------------------
# Topologia (mesh4):
#   s1 -- s2
#   |     |
#   s3 -- s4
#   h1-s1, h2-s4
#
# Portas esperadas (com topo_malha.py fornecido):
#   s1: 1->s2, 2->s3, 3->h1
#   s2: 1->s1, 2->s4
#   s3: 1->s4, 2->s1
#   s4: 1->s2, 2->s3, 3->h2
DEFAULT_PORTS = {
    1: {"to_s2": 1, "to_s3": 2, "to_h1": 3},
    2: {"to_s1": 1, "to_s4": 2},
    3: {"to_s4": 1, "to_s1": 2},
    4: {"to_s2": 1, "to_s3": 2, "to_h2": 3},
}


class SimpleSwitch13(app_manager.RyuApp):
    """Learning-switch + regras QUIC-sim para Experimentos 4/5."""

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)

        self.mac_to_port: Dict[int, Dict[str, int]] = {}
        self.port_state: Dict[Tuple[int, int], bool] = {}
        self.datapaths: Dict[int, object] = {}
        self.ports = DEFAULT_PORTS

        self.logger.info("== Controlador iniciado (EXPERIMENT=%s) ==", EXPERIMENT)

    # -----------------------------
    # PacketOut compatível (CORRIGE seus erros)
    # -----------------------------
    def send_packet_out(self, datapath, msg, in_port: int, actions):
        """
        Envia PacketOut de forma compatível com variações do Ryu:
        - Usa argumentos posicionais
        - Força buffer_id = OFP_NO_BUFFER quando enviamos data
        """
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Sempre enviamos data; então buffer_id deve ser OFP_NO_BUFFER
        data = msg.data
        out = parser.OFPPacketOut(
            datapath,                 # datapath
            ofproto.OFP_NO_BUFFER,    # buffer_id (0xffffffff)
            in_port,                  # in_port
            actions,                  # actions
            data                      # data
        )
        datapath.send_msg(out)

    # -----------------------------
    # Utilitários de flows
    # -----------------------------
    def add_flow(
        self,
        datapath,
        priority: int,
        match,
        actions,
        idle_timeout: int = 0,
        hard_timeout: int = 0,
    ):
        """Instala uma regra de fluxo no switch."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
        )
        datapath.send_msg(mod)

    def del_flow(self, datapath, match):
        """Remove flows que casam com o match (DELETE)."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        mod = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_DELETE,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            match=match,
        )
        datapath.send_msg(mod)

    # -----------------------------
    # Estado/roteamento
    # -----------------------------
    def _is_port_up(self, dpid: int, port_no: int) -> bool:
        return self.port_state.get((dpid, port_no), True)

    def _is_link_s1_s2_up(self) -> bool:
        p_s1_to_s2 = self.ports[1]["to_s2"]
        p_s2_to_s1 = self.ports[2]["to_s1"]
        return self._is_port_up(1, p_s1_to_s2) and self._is_port_up(2, p_s2_to_s1)

    def _route_quic_out_port(self, dpid: int, eth_src: str, eth_dst: str) -> Optional[int]:
        """Decide porta de saída do QUIC-sim (direcional por MAC)."""
        p = self.ports.get(dpid, {})

        h1_to_h2 = (eth_src == H1_MAC and eth_dst == H2_MAC)
        h2_to_h1 = (eth_src == H2_MAC and eth_dst == H1_MAC)

        # s1 (lado do h1)
        if dpid == 1:
            if h1_to_h2:
                if EXPERIMENT == 4:
                    # ECMP: escolhe entre s2 e s3
                    # (a linha que você pediu, só que aqui retornamos a porta)
                    return random.choice([p["to_s2"], p["to_s3"]])
                if EXPERIMENT == 5:
                    return p["to_s2"] if self._is_link_s1_s2_up() else p["to_s3"]
                return p["to_s2"]
            if h2_to_h1:
                return p["to_h1"]
            return None

        # s4 (lado do h2)
        if dpid == 4:
            if h2_to_h1:
                if EXPERIMENT == 4:
                    return random.choice([p["to_s2"], p["to_s3"]])
                if EXPERIMENT == 5:
                    return p["to_s2"] if self._is_link_s1_s2_up() else p["to_s3"]
                return p["to_s2"]
            if h1_to_h2:
                return p["to_h2"]
            return None

        # s2
        if dpid == 2:
            if h1_to_h2:
                return p["to_s4"]
            if h2_to_h1:
                if EXPERIMENT == 5 and not self._is_port_up(dpid, p["to_s1"]):
                    return None
                return p["to_s1"]
            return None

        # s3
        if dpid == 3:
            if h1_to_h2:
                return p["to_s4"]
            if h2_to_h1:
                return p["to_s1"]
            return None

        return None

    def _is_quic_packet(self, pkt: packet.Packet) -> bool:
        ip = pkt.get_protocol(ipv4.ipv4)
        if ip is None or ip.proto != 17:  # UDP
            return False
        u = pkt.get_protocol(udp.udp)
        if u is None:
            return False
        return (u.dst_port == QUIC_UDP_PORT) or (u.src_port == QUIC_UDP_PORT)

    def _quic_direction_match(self, parser, eth_src: str, eth_dst: str):
        # h2 -> h1 : udp_dst=4433
        if eth_src == H2_MAC and eth_dst == H1_MAC:
            return parser.OFPMatch(
                eth_type=0x0800,
                ip_proto=17,
                eth_src=H2_MAC,
                eth_dst=H1_MAC,
                udp_dst=QUIC_UDP_PORT,
            )
        # h1 -> h2 : udp_src=4433
        if eth_src == H1_MAC and eth_dst == H2_MAC:
            return parser.OFPMatch(
                eth_type=0x0800,
                ip_proto=17,
                eth_src=H1_MAC,
                eth_dst=H2_MAC,
                udp_src=QUIC_UDP_PORT,
            )
        return None

    def _reprogram_quic_exp5(self):
        """No Exp. 5, reprograma regras QUIC quando o link s1-s2 muda."""
        if EXPERIMENT != 5:
            return

        link_up = self._is_link_s1_s2_up()
        self.logger.info("[SDN] Exp.5: reprogramando QUIC (link s1-s2 UP=%s)", link_up)

        for dpid, dp in list(self.datapaths.items()):
            parser = dp.ofproto_parser

            # Remove regras antigas (matches amplos)
            self.del_flow(dp, parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=QUIC_UDP_PORT))
            self.del_flow(dp, parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=QUIC_UDP_PORT))

            # Reinstala proativo nos dois sentidos
            out_c2s = self._route_quic_out_port(dpid, H2_MAC, H1_MAC)
            if out_c2s is not None:
                m = self._quic_direction_match(parser, H2_MAC, H1_MAC)
                if m is not None:
                    self.add_flow(dp, 300, m, [parser.OFPActionOutput(out_c2s)])

            out_s2c = self._route_quic_out_port(dpid, H1_MAC, H2_MAC)
            if out_s2c is not None:
                m = self._quic_direction_match(parser, H1_MAC, H2_MAC)
                if m is not None:
                    self.add_flow(dp, 300, m, [parser.OFPActionOutput(out_s2c)])

    # -----------------------------
    # Eventos OpenFlow
    # -----------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        self.datapaths[datapath.id] = datapath

        # Table-miss
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

        self.logger.info("Table-miss instalada para switch %s", datapath.id)

        if EXPERIMENT == 5:
            self._reprogram_quic_exp5()

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        desc = msg.desc
        ofproto = datapath.ofproto

        port_no = desc.port_no
        link_down = bool(desc.state & ofproto.OFPPS_LINK_DOWN)
        self.port_state[(dpid, port_no)] = (not link_down)

        if link_down:
            self.logger.info("[PORT] dpid=%s port=%s => DOWN", dpid, port_no)
        else:
            self.logger.info("[PORT] dpid=%s port=%s => UP", dpid, port_no)

        # Exp 5: se mudou a porta do link s1<->s2, reprograma
        if EXPERIMENT == 5:
            s1_to_s2 = self.ports[1]["to_s2"]
            s2_to_s1 = self.ports[2]["to_s1"]
            if (dpid == 1 and port_no == s1_to_s2) or (dpid == 2 and port_no == s2_to_s1):
                self._reprogram_quic_exp5()

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        in_port = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        # ignora LLDP
        if eth.ethertype == 0x88CC:
            return

        dst = eth.dst
        src = eth.src

        # log no formato original
        self.logger.info("PACKET_IN dpid=%s src=%s dst=%s in_port=%s", dpid, src, dst, in_port)

        # learning table
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        # --- ARP SEMPRE ---
        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            out_port = self.mac_to_port[dpid].get(dst, ofproto.OFPP_FLOOD)
            actions = [parser.OFPActionOutput(out_port)]
            self.send_packet_out(datapath, msg, in_port, actions)
            return

        # --- QUIC (Exp 4/5) ---
        if self._is_quic_packet(pkt):
            out_port = self._route_quic_out_port(dpid, eth_src=src, eth_dst=dst)
            if out_port is not None:
                actions = [parser.OFPActionOutput(out_port)]
                match = self._quic_direction_match(parser, eth_src=src, eth_dst=dst)

                if match is not None:
                    hard_timeout = 1 if EXPERIMENT == 4 else 0
                    self.add_flow(
                        datapath,
                        priority=200,
                        match=match,
                        actions=actions,
                        idle_timeout=0,
                        hard_timeout=hard_timeout,
                    )

                self.send_packet_out(datapath, msg, in_port, actions)
                return
            # se não decide, cai no baseline

        # --- BASELINE learning-switch ---
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_src=src, eth_dst=dst)
            self.add_flow(datapath, priority=1, match=match, actions=actions)

        self.send_packet_out(datapath, msg, in_port, actions)
