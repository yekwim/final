# simple_switch_final.py
#
# Controlador SDN (Ryu / OpenFlow 1.3) baseado em learning-switch,
# com suporte aos Experimentos 4 e 5 do enunciado:
#
#   - Exp. 4 (ECMP-sim): alterna dinamicamente entre s2 e s3
#   - Exp. 5 (Falha de link): se link s1-s2 cair, redireciona para rota via s3
#
# Requisito: manter as saídas (prints/logs) do QUIC-sim (cliente/servidor) inalteradas.
# Este arquivo altera apenas decisões de encaminhamento no plano de dados.

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


# -----------------------------
# Configuração de Experimentos
# -----------------------------
# Se quiser alternar rápido sem editar o arquivo, rode:
#   EXPERIMENT=4 ryu-manager simple_switch_final.py
#   EXPERIMENT=5 ryu-manager simple_switch_final.py
EXPERIMENT = int(os.environ.get("EXPERIMENT", "4"))

QUIC_UDP_PORT = 4433

# MACs padrão quando Mininet é executado com "--mac"
H1_MAC = os.environ.get("H1_MAC", "00:00:00:00:00:01")
H2_MAC = os.environ.get("H2_MAC", "00:00:00:00:00:02")

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
DEFAULT_PORTS = {
    1: {"to_s2": 1, "to_s3": 2, "to_h1": 3},
    2: {"to_s1": 1, "to_s4": 2},
    3: {"to_s4": 1, "to_s1": 2},
    4: {"to_s2": 1, "to_s3": 2, "to_h2": 3},
}


class SimpleSwitch13(app_manager.RyuApp):
    # Usaremos OpenFlow 1.3
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)

        # Tabela: dpid -> {mac: porta} (learning switch)
        self.mac_to_port: Dict[int, Dict[str, int]] = {}

        # Estado de portas (para Exp. 5): (dpid, port_no) -> True (up) / False (down)
        # Se não houver informação de status, assumimos UP.
        self.port_state: Dict[Tuple[int, int], bool] = {}

        # Portas por switch (pode ser ajustado via env, se necessário)
        self.ports = DEFAULT_PORTS

        self.logger.info("== Controlador iniciado (EXPERIMENT=%s) ==", EXPERIMENT)

    # -----------------------------
    # Utilitários
    # -----------------------------
    def add_flow(self, datapath, priority, match, actions, buffer_id=None):
        """Instala uma regra de fluxo no switch."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]

        if buffer_id is not None:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                buffer_id=buffer_id,
                priority=priority,
                match=match,
                instructions=inst,
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath,
                priority=priority,
                match=match,
                instructions=inst,
            )

        datapath.send_msg(mod)

    def _is_port_up(self, dpid: int, port_no: int) -> bool:
        return self.port_state.get((dpid, port_no), True)

    def _choose_ecmp_port(self, dpid: int, candidates: Tuple[int, int]) -> int:
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
        # Se ambas aparentam DOWN, mantém comportamento "mais seguro":
        # devolve p2 (arbitrário) e o protocolo QUIC-sim vai retransmitir.
        return p2

    def _route_quic_out_port(self, dpid: int, src_mac: str, in_port: int) -> Optional[int]:
        """Decide a porta de saída para tráfego QUIC-sim.

        Para funcionar nos dois sentidos (h1<->h2), usamos MAC de origem.
        - Se src_mac == H1_MAC: tráfego saindo de h1 rumo a h2 (edge s1)
        - Se src_mac == H2_MAC: tráfego saindo de h2 rumo a h1 (edge s4)

        Para switches intermediários, encaminhamos para o próximo hop do caminho escolhido.
        """
        p = self.ports.get(dpid, {})

        # --- Edge: s1 (lado do servidor h1)
        if dpid == 1:
            if src_mac == H1_MAC:
                # h1 -> (s1) -> ... -> h2
                if EXPERIMENT == 4:
                    return self._choose_ecmp_port(dpid, (p["to_s2"], p["to_s3"]))
                if EXPERIMENT == 5:
                    # Preferir caminho superior via s2, mas se a porta para s2 cair, desvia para s3.
                    if self._is_port_up(dpid, p["to_s2"]):
                        return p["to_s2"]
                    return p["to_s3"]
                # fallback: caminho superior
                return p["to_s2"]
            else:
                # tráfego voltando em direção a h1
                return p["to_h1"]

        # --- Edge: s4 (lado do cliente h2)
        if dpid == 4:
            if src_mac == H2_MAC:
                # h2 -> (s4) -> ... -> h1
                if EXPERIMENT == 4:
                    return self._choose_ecmp_port(dpid, (p["to_s2"], p["to_s3"]))
                if EXPERIMENT == 5:
                    if self._is_port_up(dpid, p["to_s2"]):
                        return p["to_s2"]
                    return p["to_s3"]
                return p["to_s2"]
            else:
                # tráfego voltando em direção a h2
                return p["to_h2"]

        # --- Intermediários
        if dpid == 2:
            # Se veio de s1 (ou s4), segue para s4 (ou s1) conforme porta de entrada
            # (topologia é linha s1-s2-s4)
            if in_port == p["to_s1"]:
                return p["to_s4"]
            return p["to_s1"]

        if dpid == 3:
            # linha s1-s3-s4
            if in_port == p["to_s1"]:
                return p["to_s4"]
            return p["to_s1"]

        return None

    def _is_quic_packet(self, pkt: packet.Packet) -> bool:
        ip = pkt.get_protocol(ipv4.ipv4)
        if ip is None or ip.proto != 17:
            return False
        u = pkt.get_protocol(udp.udp)
        if u is None:
            return False
        return (u.dst_port == QUIC_UDP_PORT) or (u.src_port == QUIC_UDP_PORT)

    # -----------------------------
    # Eventos OpenFlow
    # -----------------------------
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Chamado quando o switch conecta ao controlador.
        Instala a regra table-miss: pacotes não casados vão para o controlador.
        """
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

        self.logger.info("Table-miss instalada para switch %s", datapath.id)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        """Atualiza estado de portas (UP/DOWN) para suportar Exp. 5."""
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        reason = msg.reason
        desc = msg.desc

        ofproto = datapath.ofproto

        port_no = desc.port_no
        # Alguns motivos:
        #   OFPPR_ADD, OFPPR_DELETE, OFPPR_MODIFY
        # E o campo desc.state contém OFPPS_LINK_DOWN quando o link está down.
        link_down = bool(desc.state & ofproto.OFPPS_LINK_DOWN)

        # Marcamos UP/DOWN independentemente do motivo, usando o state do port.
        self.port_state[(dpid, port_no)] = (not link_down)

        if link_down:
            self.logger.info("[PORT] dpid=%s port=%s => DOWN", dpid, port_no)
        else:
            self.logger.info("[PORT] dpid=%s port=%s => UP", dpid, port_no)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """Tratamento de pacotes enviados ao controlador (packet-in)."""
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        in_port = msg.match['in_port']

        # Decodificar o pacote
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        # Ignora LLDP (usado para descoberta de topologia)
        if eth.ethertype == 0x88cc:
            return

        dst = eth.dst
        src = eth.src

        # Mantém o log original (requisito de manter as saídas/prints)
        self.logger.info("PACKET_IN dpid=%s src=%s dst=%s in_port=%s",
                         dpid, src, dst, in_port)

        # Inicializa tabela para este switch se ainda não existir
        self.mac_to_port.setdefault(dpid, {})

        # Aprende MAC de origem -> porta de entrada
        self.mac_to_port[dpid][src] = in_port

        # -----------------------------
        # Regras específicas QUIC-sim (Exp. 4 / 5)
        # -----------------------------
        if self._is_quic_packet(pkt):
            out_port = self._route_quic_out_port(dpid, src_mac=src, in_port=in_port)

            if out_port is not None:
                actions = [parser.OFPActionOutput(out_port)]

                # Instalamos duas regras para cobrir os dois sentidos do fluxo QUIC-sim:
                # - udp_dst=4433 (pacotes do cliente para o servidor)
                # - udp_src=4433 (respostas do servidor)
                #
                # Como não fazemos parsing de payload, só L2/L3/L4.
                match_dst = parser.OFPMatch(
                    eth_type=0x0800,
                    ip_proto=17,
                    udp_dst=QUIC_UDP_PORT
                )
                match_src = parser.OFPMatch(
                    eth_type=0x0800,
                    ip_proto=17,
                    udp_src=QUIC_UDP_PORT
                )

                # Prioridade 200: acima do learning-switch (prioridade 1).
                # Assim, QUIC-sim respeita as políticas do experimento.
                self.add_flow(datapath, 200, match_dst, actions)
                self.add_flow(datapath, 200, match_src, actions)

                # Packet-out do pacote atual
                data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
                out = parser.OFPPacketOut(
                    datapath=datapath,
                    buffer_id=msg.buffer_id,
                    in_port=in_port,
                    actions=actions,
                    data=data
                )
                datapath.send_msg(out)
                return
            # Se não conseguimos decidir (dpid inesperado), cai no learning-switch.

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
            else:
                self.add_flow(datapath, 1, match, actions)

        # Envia o pacote atual (packet-out)
        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)
