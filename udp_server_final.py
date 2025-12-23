# udp_server_final.py
#
# Servidor "QUIC-sim" baseado em UDP:
# - Porta 4433 (porta típica para testes QUIC)
# - Simula atraso de rede
# - Simula perda de pacotes
# - Responde com ACK contendo o seq

import base64
from collections import defaultdict

import socket
import json
import random
import time

HOST = "0.0.0.0"
PORT = 4433

# Probabilidade de "perder" um pacote recebido (0.3 = 30%)
LOSS_PROB = 0.3

# Atraso máximo artificial na resposta (em segundos)
MAX_DELAY = 0.5

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((HOST, PORT))

print(f"[SERVIDOR] QUIC-sim escutando em {HOST}:{PORT}")
print(f"[SERVIDOR] LOSS_PROB={LOSS_PROB}, MAX_DELAY={MAX_DELAY}s")

def rebuild_file(filename, file_info):
    """Reconstrói o arquivo a partir dos chunks recebidos."""
    chunks_dict = file_info["chunks"]
    total = file_info["total"]

    # Ordena pelos seq
    ordered_seqs = sorted(chunks_dict.keys())
    if len(ordered_seqs) != total:
        print(f"[SERVIDOR] Aviso: número de chunks ({len(ordered_seqs)}) diferente de total ({total})")

    output_name = f"recebido_{filename}"
    with open(output_name, "wb") as f:
        for seq in ordered_seqs:
            f.write(chunks_dict[seq])

    print(f"[SERVIDOR] Arquivo reconstruído como {output_name}")

# Armazena chunks por arquivo: filename -> { "total": int, "chunks": {seq: bytes} }
files_state = defaultdict(lambda: {"total": None, "chunks": {}})

while True:
    data, addr = sock.recvfrom(2048)
    now = time.time()
    try:
        packet = json.loads(data.decode())
    except Exception:
        packet = {"type": "unknown", "raw": data.decode(errors="ignore")}

    ptype = packet.get("type", "unknown")
    seq = packet.get("seq", "?")
    msg = packet.get("msg", "")

    print(f"[RECV {now:.3f}] de {addr} -> type={ptype}, seq={seq}, msg={msg}")

    # Decisão de "perder" o pacote
    if random.random() < LOSS_PROB:
        print(f"  -> [DROP] simulando perda do pacote seq={seq}")
        continue

    # Atraso artificial
    delay = random.uniform(0, MAX_DELAY)
    time.sleep(delay)

    # --- NOVO: tratamento de file_chunk ---
    if ptype == "file_chunk":
        filename = packet.get("filename", "arquivo.bin")
        total = packet["total"]
        b64_data = packet["data"]

        chunk_bytes = base64.b64decode(b64_data)

        file_info = files_state[filename]

        # define total na primeira vez
        if file_info["total"] is None:
            file_info["total"] = total

        file_info["chunks"][seq] = chunk_bytes

        print(f"[SERVIDOR] Recebido chunk seq={seq} do arquivo {filename} "
              f"({len(file_info['chunks'])}/{file_info['total']})")

        # Envia ACK específico
        ack = {
            "type": "ack_chunk",
            "seq": seq
        }
        sock.sendto(json.dumps(ack).encode(), addr)

        # Se completou todos os chunks, reconstrói
        if len(file_info["chunks"]) == file_info["total"]:
            rebuild_file(filename, file_info)

        # Já tratamos este tipo de pacote, volta pro início do loop
        continue

    response = {
        "type": "ack",
        "seq": seq,
        "info": f"ack-from-server (delay={delay:.3f}s)"
    }
    resp_bytes = json.dumps(response).encode()
    sock.sendto(resp_bytes, addr)

    print(f"  -> [SEND] ACK seq={seq} para {addr} (delay={delay:.3f}s)")
