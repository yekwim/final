# simple_switch_final.py
#
# Controlador SDN (Ryu / OpenFlow 1.3) para os Experimentos 4 e 5:
#   - Exp. 4 (ECMP-sim): Alterna caminhos entre s2 e s3 usando hard_timeout=1.
#   - Exp. 5 (Falha de link): Redireciona tráfego via s3 se s1-s2 cair.

from __future__ import annotations
import os
import random
from typing import Dict, Optional, Tuple

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ipv4, udp, ether_types

# --- Configurações ---
EXPERIMENT = int(os.environ.get("EXPERIMENT", "4"))
QUIC_UDP_PORT = 4433
H1_MAC = os.environ.get("H1_MAC", "00:00:00:00:00:01")
H2_MAC = os.environ.get("H2_MAC", "00:00:00:00:00:02")

# Mapeamento de portas baseado no topo_malha.py
DEFAULT_PORTS = {
    1: {"to_s2": 1, "to_s3": 2, "to_h1": 3},
    2: {"to_s1": 1, "to_s4": 2},
    3: {"to_s4": 1, "to_s1": 2},
    4: {"to_s2": 1, "to_s3": 2, "to_h2": 3},
}

class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.mac_to_port: Dict[int, Dict[str, int]] = {}
        self.port_state: Dict[Tuple[int, int], bool] = {}
        self.datapaths: Dict[int, object] = {}
        self.ports = DEFAULT_PORTS
        self.logger.info("== Controlador Pronto (EXPERIMENT=%s) ==", EXPERIMENT)

    # --- Utilitários de Fluxo ---
    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        
        if buffer_id is not None:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    priority=priority, match=match,
                                    instructions=inst, idle_timeout=idle_timeout,
                                    hard_timeout=hard_timeout)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                    match=match, instructions=inst,
                                    idle_timeout=idle_timeout,
                                    hard_timeout=hard_timeout)
        datapath.send_msg(mod)

    def del_flow(self, datapath, match):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        mod = parser.OFPFlowMod(datapath=datapath, command=ofproto.OFPFC_DELETE,
                                out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
                                match=match)
        datapath.send_msg(mod)

    def send_packet_out(self, datapath, msg, in_port, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    # --- Lógica de Roteamento ---
    def _is_port_up(self, dpid, port_no):
        return self.port_state.get((dpid, port_no), True)

    def _is_link_s1_s2_up(self):
        return self._is_port_up(1, self.ports[1]["to_s2"]) and self._is_port_up(2, self.ports[2]["to_s1"])

    def _route_quic(self, dpid, eth_src, eth_dst):
        p = self.ports.get(dpid, {})
        h1_to_h2 = (eth_src == H1_MAC and eth_dst == H2_MAC)
        h2_to_h1 = (eth_src == H2_MAC and eth_dst == H1_MAC)

        if dpid == 1:
            if h1_to_h2:
                if EXPERIMENT == 4: return random.choice([p["to_s2"], p["to_s3"]])
                if EXPERIMENT == 5: return p["to_s2"] if self._is_link_s1_s2_up() else p["to_s3"]
                return p["to_s2"]
            return p["to_h1"] if h2_to_h1 else None

        if dpid == 4:
            if h2_to_h1:
                if EXPERIMENT == 4: return random.choice([p["to_s2"], p["to_s3"]])
                if EXPERIMENT == 5: return p["to_s2"] if self._is_link_s1_s2_up() else p["to_s3"]
                return p["to_s2"]
            return p["to_h2"] if h1_to_h2 else None

        if dpid == 2: return p["to_s4"] if h1_to_h2 else (p["to_s1"] if h2_to_h1 else None)
        if dpid == 3: return p["to_s4"] if h1_to_h2 else (p["to_s1"] if h2_to_h1 else None)
        return None

    def _get_quic_match(self, parser, eth_src, eth_dst):
        if eth_src == H1_MAC: # Servidor -> Cliente
            return parser.OFPMatch(eth_type=0x0800, ip_proto=17, eth_src=H1_MAC, eth_dst=H2_MAC, udp_src=QUIC_UDP_PORT)
        return parser.OFPMatch(eth_type=0x0800, ip_proto=17, eth_src=H2_MAC, eth_dst=H1_MAC, udp_dst=QUIC_UDP_PORT)

    def _reprogram_exp5(self):
        if EXPERIMENT != 5: return
        self.logger.info("[SDN] Link s1-s2 status mudou. Reprogramando...")
        for dp in self.datapaths.values():
            self.del_flow(dp, dp.ofproto_parser.OFPMatch(eth_type=0x0800, ip_proto=17))

    # --- Handlers de Eventos ---
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        self.datapaths[datapath.id] = datapath
        match = datapath.ofproto_parser.OFPMatch()
        actions = [datapath.ofproto_parser.OFPActionOutput(datapath.ofproto.OFPP_CONTROLLER, datapath.ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        self.port_state[(msg.datapath.id, msg.desc.port_no)] = not bool(msg.desc.state & msg.datapath.ofproto.OFPPS_LINK_DOWN)
        if (msg.datapath.id in [1, 2]): self._reprogram_exp5()

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == ether_types.ETH_TYPE_LLDP: return

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][eth.src] = in_port

        # Lógica QUIC
        ip = pkt.get_protocol(ipv4.ipv4)
        udp_pkt = pkt.get_protocol(udp.udp)
        if ip and udp_pkt and (udp_pkt.src_port == QUIC_UDP_PORT or udp_pkt.dst_port == QUIC_UDP_PORT):
            out_port = self._route_quic(dpid, eth.src, eth.dst)
            if out_port:
                actions = [parser.OFPActionOutput(out_port)]
                h_timeout = 1 if EXPERIMENT == 4 else 0
                self.add_flow(datapath, 200, self._get_quic_match(parser, eth.src, eth.dst), actions, hard_timeout=h_timeout)
                self.send_packet_out(datapath, msg, in_port, actions)
                return

        # Learning Switch (Baseline)
        out_port = self.mac_to_port[dpid].get(eth.dst, datapath.ofproto.OFPP_FLOOD)
        actions = [parser.OFPActionOutput(out_port)]
        if out_port != datapath.ofproto.OFPP_FLOOD:
            self.add_flow(datapath, 1, parser.OFPMatch(in_port=in_port, eth_dst=eth.dst), actions)
        self.send_packet_out(datapath, msg, in_port, actions)