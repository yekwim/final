# simple_switch_final.py
#
# Controlador SDN (Ryu / OpenFlow 1.3) baseado em learning-switch,
# com suporte aos Experimentos 4 e 5 do enunciado:
#
#   - Exp. 4 (ECMP-sim): alterna dinamicamente entre s2 e s3
#   - Exp. 5 (Falha de link): se link s1-s2 cair, redireciona para rota via s3
<<<<<<< HEAD
=======
#
# Requisito: manter as saídas (prints/logs) do QUIC-sim (cliente/servidor) inalteradas.
# Este arquivo altera apenas decisões de encaminhamento no plano de dados.
#
# Como rodar rapidamente:
#   EXPERIMENT=4 ryu-manager simple_switch_final.py
#   EXPERIMENT=5 ryu-manager simple_switch_final.py
>>>>>>> parent of ccdc713 (Up)

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
<<<<<<< HEAD
from ryu.lib.packet import ether_types

=======

# -----------------------------
# Configuração de Experimentos
# -----------------------------
>>>>>>> parent of ccdc713 (Up)
EXPERIMENT = int(os.environ.get("EXPERIMENT", "4"))

# QUIC-sim usa UDP/4433 (conforme how-to-experimental.md)
QUIC_UDP_PORT = 4433

# MACs padrão quando Mininet é executado com "--mac"
H1_MAC = os.environ.get("H1_MAC", "00:00:00:00:00:01")
H2_MAC = os.environ.get("H2_MAC", "00:00:00:00:00:02")

<<<<<<< HEAD
=======
# -----------------------------
# Mapeamento de portas (DEFAULT)
# -----------------------------
# Observação importante:
# As portas podem variar se a ordem de criação dos links mudar.
# O mapeamento abaixo é o "default" esperado para o topo_malha.py fornecido
# (ordem de addLink) e Mininet/OVS padrão.
#
# Se necessário, confirme no Mininet:
#   mininet> sh ovs-ofctl show s1 -O OpenFlow13
#   mininet> sh ovs-ofctl show s2 -O OpenFlow13
#   mininet> sh ovs-ofctl show s3 -O OpenFlow13
#   mininet> sh ovs-ofctl show s4 -O OpenFlow13
#
# Topologia (do enunciado):
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
>>>>>>> parent of ccdc713 (Up)
DEFAULT_PORTS = {
    1: {"to_s2": 1, "to_s3": 2, "to_h1": 3},
    2: {"to_s1": 1, "to_s4": 2},
    3: {"to_s4": 1, "to_s1": 2},
    4: {"to_s2": 1, "to_s3": 2, "to_h2": 3},
}


class SimpleSwitch13(app_manager.RyuApp):
    """Learning-switch (baseline) + regras direcionais QUIC-sim para Experimentos 4/5."""

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)

        # Tabela: dpid -> {mac: porta} (learning switch)
        self.mac_to_port: Dict[int, Dict[str, int]] = {}

        # Estado de portas: (dpid, port_no) -> True (up) / False (down)
        # Se não houver informação de status, assumimos UP.
        self.port_state: Dict[Tuple[int, int], bool] = {}

        # Mantém datapaths conectados (necessário para reprogramar regras no Exp. 5)
        self.datapaths: Dict[int, object] = {}

        # Portas por switch (pode ser ajustado via env, se necessário)
        self.ports = DEFAULT_PORTS
<<<<<<< HEAD
        self.logger.info("== Controlador iniciado (EXPERIMENT=%s) ==", EXPERIMENT)

    def _packet_out(self, datapath, msg, in_port, actions):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data
        try:
            out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                      in_port=in_port, actions=actions, data=data)
        except TypeError:
            out = parser.OFPPacketOut(datapath, msg.buffer_id, in_port, actions, data)
        datapath.send_msg(out)

    def add_flow(self, datapath, priority, match, actions,
                 buffer_id=None, idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        try:
            if buffer_id is not None:
                mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                        priority=priority, match=match,
                                        instructions=inst,
                                        idle_timeout=idle_timeout,
                                        hard_timeout=hard_timeout)
            else:
                mod = parser.OFPFlowMod(datapath=datapath,
                                        priority=priority, match=match,
                                        instructions=inst,
                                        idle_timeout=idle_timeout,
                                        hard_timeout=hard_timeout)
            datapath.send_msg(mod)
            return
        except TypeError:
            pass

        try:
            if buffer_id is not None:
                mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                        priority=priority, match=match,
                                        inst=inst,
                                        idle_timeout=idle_timeout,
                                        hard_timeout=hard_timeout)
            else:
                mod = parser.OFPFlowMod(datapath=datapath,
                                        priority=priority, match=match,
                                        inst=inst,
                                        idle_timeout=idle_timeout,
                                        hard_timeout=hard_timeout)
            datapath.send_msg(mod)
            return
        except TypeError:
            pass

        cookie = 0
        cookie_mask = 0
        table_id = 0
        command = ofproto.OFPFC_ADD
        out_port = ofproto.OFPP_ANY
        out_group = ofproto.OFPG_ANY
        flags = 0

        if buffer_id is None:
            buffer_id = ofproto.OFP_NO_BUFFER

        mod = parser.OFPFlowMod(datapath, cookie, cookie_mask, table_id, command,
                                idle_timeout, hard_timeout, priority, buffer_id,
                                out_port, out_group, flags, match, inst)
        datapath.send_msg(mod)

    def del_flow(self, datapath, match):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        mod = parser.OFPFlowMod(datapath=datapath, command=ofproto.OFPFC_DELETE,
                                out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
                                match=match)
        datapath.send_msg(mod)

=======

        self.logger.info("== Controlador iniciado (EXPERIMENT=%s) ==", EXPERIMENT)

    def _packet_out(self, datapath, msg, in_port, actions):
        """Envia PacketOut de forma compatível com diferentes versões do Ryu."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        # Alguns builds aceitam keywords; outros exigem argumentos posicionais.
        try:
            out = parser.OFPPacketOut(
                datapath=datapath,
                buffer_id=msg.buffer_id,
                in_port=in_port,
                actions=actions,
                data=data,
            )
        except TypeError:
            out = parser.OFPPacketOut(datapath, msg.buffer_id, in_port, actions, data)

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
        buffer_id=None,
        idle_timeout: int = 0,
        hard_timeout: int = 0,
    ):
        """Instala uma regra de fluxo no switch (compatível com variações do Ryu)."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst_list = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        # Alguns builds antigos do Ryu aceitam 'inst' em vez de 'instructions'.
        # Para máxima compatibilidade, tentamos primeiro 'instructions' e, se falhar, usamos 'inst'.
        kwargs = dict(
            datapath=datapath,
            priority=priority,
            match=match,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout,
        )
        if buffer_id is not None:
            kwargs["buffer_id"] = buffer_id

        try:
            kwargs_i = dict(kwargs)
            kwargs_i["instructions"] = inst_list
            mod = parser.OFPFlowMod(**kwargs_i)
        except TypeError:
            kwargs_i = dict(kwargs)
            kwargs_i["inst"] = inst_list
            mod = parser.OFPFlowMod(**kwargs_i)

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
>>>>>>> parent of ccdc713 (Up)
    def _is_port_up(self, dpid: int, port_no: int) -> bool:
        return self.port_state.get((dpid, port_no), True)

    def _is_link_s1_s2_up(self) -> bool:
<<<<<<< HEAD
=======
        """Link s1<->s2 (superior) está UP? Checa os dois lados quando possível."""
>>>>>>> parent of ccdc713 (Up)
        p_s1_to_s2 = self.ports[1]["to_s2"]
        p_s2_to_s1 = self.ports[2]["to_s1"]
        return self._is_port_up(1, p_s1_to_s2) and self._is_port_up(2, p_s2_to_s1)

    def _choose_ecmp_port(self, dpid: int, candidates: Tuple[int, int]) -> int:
<<<<<<< HEAD
        p1, p2 = candidates
        p1_up = self._is_port_up(dpid, p1)
        p2_up = self._is_port_up(dpid, p2)
        if p1_up and p2_up: return random.choice([p1, p2])
        if p1_up: return p1
        if p2_up: return p2
        return p2

    def _route_quic_out_port(self, dpid: int, eth_src: str, eth_dst: str, in_port: int) -> Optional[int]:
=======
        """Escolhe aleatoriamente uma porta UP entre duas opções.
        Se uma estiver DOWN, força a outra.
        """
        p1, p2 = candidates
        p1_up = self._is_port_up(dpid, p1)
        p2_up = self._is_port_up(dpid, p2)

        if p1_up and p2_up:
            return random.choice([p1, p2])
        if p1_up:
            return p1
        if p2_up:
            return p2
        # Se ambas aparentam DOWN, devolve uma opção arbitrária.
        return p2

    def _route_quic_out_port(
        self,
        dpid: int,
        eth_src: str,
        eth_dst: str,
        in_port: int,
    ) -> Optional[int]:
        """Decide porta de saída do QUIC-sim (direcional por MAC)."""
>>>>>>> parent of ccdc713 (Up)
        p = self.ports.get(dpid, {})

        h1_to_h2 = (eth_src == H1_MAC and eth_dst == H2_MAC)
        h2_to_h1 = (eth_src == H2_MAC and eth_dst == H1_MAC)

        # Edge s1 (lado do h1)
        if dpid == 1:
            if h1_to_h2:
<<<<<<< HEAD
                if EXPERIMENT == 4: return self._choose_ecmp_port(dpid, (p["to_s2"], p["to_s3"]))
                if EXPERIMENT == 5: return p["to_s2"] if self._is_link_s1_s2_up() else p["to_s3"]
                return p["to_s2"]
            if h2_to_h1: return p["to_h1"]
        if dpid == 4:
            if h2_to_h1:
                if EXPERIMENT == 4: return self._choose_ecmp_port(dpid, (p["to_s2"], p["to_s3"]))
                if EXPERIMENT == 5: return p["to_s2"] if self._is_link_s1_s2_up() else p["to_s3"]
                return p["to_s2"]
            if h1_to_h2: return p["to_h2"]
        if dpid == 2:
            if h1_to_h2: return p["to_s4"]
            if h2_to_h1:
                if EXPERIMENT == 5 and not self._is_port_up(dpid, p["to_s1"]): return None
                return p["to_s1"]
        if dpid == 3:
            if h1_to_h2: return p["to_s4"]
            if h2_to_h1: return p["to_s1"]
=======
                if EXPERIMENT == 4:
                    return self._choose_ecmp_port(dpid, (p["to_s2"], p["to_s3"]))
                if EXPERIMENT == 5:
                    # Se o link superior s1-s2 caiu, forçamos via s3
                    return p["to_s2"] if self._is_link_s1_s2_up() else p["to_s3"]
                return p["to_s2"]
            if h2_to_h1:
                return p["to_h1"]
            return None

        # Edge s4 (lado do h2)
        if dpid == 4:
            if h2_to_h1:
                if EXPERIMENT == 4:
                    return self._choose_ecmp_port(dpid, (p["to_s2"], p["to_s3"]))
                if EXPERIMENT == 5:
                    # Mesmo com s4-s2 UP, se s1-s2 caiu, não há como chegar em s1 por s2.
                    return p["to_s2"] if self._is_link_s1_s2_up() else p["to_s3"]
                return p["to_s2"]
            if h1_to_h2:
                return p["to_h2"]
            return None

        # Intermediário s2 (caminho superior)
        if dpid == 2:
            if h1_to_h2:
                return p["to_s4"]
            if h2_to_h1:
                # Se o link s2->s1 caiu (Exp. 5), não tenta encaminhar por ele.
                if EXPERIMENT == 5 and not self._is_port_up(dpid, p["to_s1"]):
                    return None
                return p["to_s1"]
            return None

        # Intermediário s3 (caminho inferior)
        if dpid == 3:
            if h1_to_h2:
                return p["to_s4"]
            if h2_to_h1:
                return p["to_s1"]
            return None

>>>>>>> parent of ccdc713 (Up)
        return None

    def _is_quic_packet(self, pkt: packet.Packet) -> bool:
        ip = pkt.get_protocol(ipv4.ipv4)
<<<<<<< HEAD
        if ip is None or ip.proto != 17: return False
        u = pkt.get_protocol(udp.udp)
        if u is None: return False
        return (u.dst_port == QUIC_UDP_PORT) or (u.src_port == QUIC_UDP_PORT)

    def _quic_direction_match(self, parser, eth_src: str, eth_dst: str):
        if eth_src == H2_MAC and eth_dst == H1_MAC:
            return parser.OFPMatch(eth_type=0x0800, ip_proto=17, eth_src=H2_MAC, eth_dst=H1_MAC, udp_dst=QUIC_UDP_PORT)
        if eth_src == H1_MAC and eth_dst == H2_MAC:
            return parser.OFPMatch(eth_type=0x0800, ip_proto=17, eth_src=H1_MAC, eth_dst=H2_MAC, udp_src=QUIC_UDP_PORT)
        return None

    def _reprogram_quic_exp5(self):
        if EXPERIMENT != 5: return
        link_up = self._is_link_s1_s2_up()
        self.logger.info("[SDN] Exp.5: reprogramando QUIC (link s1-s2 UP=%s)", link_up)
        for dpid, dp in list(self.datapaths.items()):
            parser = dp.ofproto_parser
            self.del_flow(dp, parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=QUIC_UDP_PORT))
            self.del_flow(dp, parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=QUIC_UDP_PORT))
            out_port_c2s = self._route_quic_out_port(dpid, H2_MAC, H1_MAC, in_port=0)
            if out_port_c2s is not None:
                self.add_flow(dp, 300, self._quic_direction_match(parser, H2_MAC, H1_MAC), [parser.OFPActionOutput(out_port_c2s)])
            out_port_s2c = self._route_quic_out_port(dpid, H1_MAC, H2_MAC, in_port=0)
            if out_port_s2c is not None:
                self.add_flow(dp, 300, self._quic_direction_match(parser, H1_MAC, H2_MAC), [parser.OFPActionOutput(out_port_s2c)])

=======
        if ip is None or ip.proto != 17:  # UDP
            return False
        u = pkt.get_protocol(udp.udp)
        if u is None:
            return False
        return (u.dst_port == QUIC_UDP_PORT) or (u.src_port == QUIC_UDP_PORT)

    def _quic_direction_match(self, parser, eth_src: str, eth_dst: str):
        """Cria match direcional para QUIC-sim evitando colisão de regras."""
        # h2 -> h1 (cliente->servidor): udp_dst=4433
        if eth_src == H2_MAC and eth_dst == H1_MAC:
            return parser.OFPMatch(
                eth_type=0x0800,
                ip_proto=17,
                eth_src=H2_MAC,
                eth_dst=H1_MAC,
                udp_dst=QUIC_UDP_PORT,
            )
        # h1 -> h2 (servidor->cliente): udp_src=4433
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

            # Remove regras QUIC antigas (broad match)
            self.del_flow(dp, parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=QUIC_UDP_PORT))
            self.del_flow(dp, parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=QUIC_UDP_PORT))

            # Instala regras atuais (proativas) para os dois sentidos
            # h2->h1
            out_port_c2s = self._route_quic_out_port(dpid, H2_MAC, H1_MAC, in_port=0)
            if out_port_c2s is not None:
                match_c2s = self._quic_direction_match(parser, H2_MAC, H1_MAC)
                actions = [parser.OFPActionOutput(out_port_c2s)]
                self.add_flow(dp, 300, match_c2s, actions)

            # h1->h2
            out_port_s2c = self._route_quic_out_port(dpid, H1_MAC, H2_MAC, in_port=0)
            if out_port_s2c is not None:
                match_s2c = self._quic_direction_match(parser, H1_MAC, H2_MAC)
                actions = [parser.OFPActionOutput(out_port_s2c)]
                self.add_flow(dp, 300, match_s2c, actions)

    # -----------------------------
    # Eventos OpenFlow
    # -----------------------------
>>>>>>> parent of ccdc713 (Up)
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Chamado quando o switch conecta ao controlador.
        Instala a regra table-miss: pacotes não casados vão para o controlador.
        """
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
<<<<<<< HEAD
        self.datapaths[datapath.id] = datapath
=======

        # registra datapath
        self.datapaths[datapath.id] = datapath

>>>>>>> parent of ccdc713 (Up)
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)
        self.logger.info("Table-miss instalada para switch %s", datapath.id)
        if EXPERIMENT == 5: self._reprogram_quic_exp5()

        self.logger.info("Table-miss instalada para switch %s", datapath.id)

        # Para Exp.5, podemos instalar proativamente as regras já no connect
        if EXPERIMENT == 5:
            self._reprogram_quic_exp5()

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        """Atualiza estado de portas (UP/DOWN) e reprograma Exp. 5."""
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
<<<<<<< HEAD
        port_no = msg.desc.port_no
        link_down = bool(msg.desc.state & datapath.ofproto.OFPPS_LINK_DOWN)
        self.port_state[(dpid, port_no)] = (not link_down)
        if link_down: self.logger.info("[PORT] dpid=%s port=%s => DOWN", dpid, port_no)
        else: self.logger.info("[PORT] dpid=%s port=%s => UP", dpid, port_no)
=======
        desc = msg.desc
        ofproto = datapath.ofproto

        port_no = desc.port_no
        link_down = bool(desc.state & ofproto.OFPPS_LINK_DOWN)
        self.port_state[(dpid, port_no)] = (not link_down)

        if link_down:
            self.logger.info("[PORT] dpid=%s port=%s => DOWN", dpid, port_no)
        else:
            self.logger.info("[PORT] dpid=%s port=%s => UP", dpid, port_no)

        # Exp. 5: se o link s1-s2 (em qualquer lado) mudar, reprograma regras QUIC
>>>>>>> parent of ccdc713 (Up)
        if EXPERIMENT == 5:
            s1_to_s2 = self.ports[1]["to_s2"]
            s2_to_s1 = self.ports[2]["to_s1"]
            if (dpid == 1 and port_no == s1_to_s2) or (dpid == 2 and port_no == s2_to_s1):
                self._reprogram_quic_exp5()

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """Tratamento de pacotes enviados ao controlador (packet-in)."""
        msg = ev.msg
        datapath = msg.datapath
<<<<<<< HEAD
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match["in_port"]
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth.ethertype == 0x88CC: return
        dst, src = eth.dst, eth.src
        self.logger.info("PACKET_IN dpid=%s src=%s dst=%s in_port=%s", datapath.id, src, dst, in_port)
        self.mac_to_port.setdefault(datapath.id, {})
        self.mac_to_port[datapath.id][src] = in_port

        if self._is_quic_packet(pkt):
            out_port = self._route_quic_out_port(datapath.id, eth_src=src, eth_dst=dst, in_port=in_port)
            if out_port is not None:
                actions = [parser.OFPActionOutput(out_port)]
                match = self._quic_direction_match(parser, eth_src=src, eth_dst=dst)
                if match is not None:
                    h_timeout = 1 if EXPERIMENT == 4 else 0
                    self.add_flow(datapath, 200, match, actions, hard_timeout=h_timeout)
                self._packet_out(datapath, msg, in_port, actions)
                return

        if dst in self.mac_to_port[datapath.id]:
            out_port = self.mac_to_port[datapath.id][dst]
        else:
            out_port = ofproto.OFPP_FLOOD
        actions = [parser.OFPActionOutput(out_port)]
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            self.add_flow(datapath, 1, match, actions, msg.buffer_id if msg.buffer_id != ofproto.OFP_NO_BUFFER else None)
        self._packet_out(datapath, msg, in_port, actions)
=======
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        in_port = msg.match["in_port"]

        # Decodificar o pacote
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        # Ignora LLDP (usado para descoberta de topologia)
        if eth.ethertype == 0x88CC:
            return

        dst = eth.dst
        src = eth.src

        # Mantém o log original
        self.logger.info("PACKET_IN dpid=%s src=%s dst=%s in_port=%s", dpid, src, dst, in_port)

        # Inicializa tabela para este switch se ainda não existir
        self.mac_to_port.setdefault(dpid, {})

        # Aprende MAC de origem -> porta de entrada
        self.mac_to_port[dpid][src] = in_port

        # -----------------------------
        # Regras específicas QUIC-sim (Exp. 4 / 5)
        # -----------------------------
        if self._is_quic_packet(pkt):
            out_port = self._route_quic_out_port(dpid, eth_src=src, eth_dst=dst, in_port=in_port)

            if out_port is not None:
                actions = [parser.OFPActionOutput(out_port)]

                # Match direcional para não conflitar udp_src vs udp_dst
                match = self._quic_direction_match(parser, eth_src=src, eth_dst=dst)

                if match is not None:
                    # Exp.4: fluxo curto para permitir "alterna dinamicamente" (random a cada re-instalação)
                    hard_timeout = 1 if EXPERIMENT == 4 else 0

                    # Prioridade acima do learning-switch (1)
                    self.add_flow(
                        datapath,
                        priority=200,
                        match=match,
                        actions=actions,
                        idle_timeout=0,
                        hard_timeout=hard_timeout,
                    )

                # Packet-out do pacote atual
                self._packet_out(datapath, msg, in_port, actions)
                return
            # Se não conseguimos decidir, cai no learning-switch.

        # -----------------------------
        # Learning-switch (baseline)
        # -----------------------------
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Se já sabemos a porta de saída e não é FLOOD, instalamos fluxo
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)

            if msg.buffer_id != ofproto.OFP_NO_BUFFER:
                self.add_flow(datapath, 1, match, actions, msg.buffer_id)
                return
            self.add_flow(datapath, 1, match, actions)

        # Envia o pacote atual (packet-out)
        self._packet_out(datapath, msg, in_port, actions)
>>>>>>> parent of ccdc713 (Up)
