# udp_client_final.py
#
# Cliente "QUIC-sim" baseado em UDP:
# - Envia handshake + vários pacotes "data"
# - Cada pacote tem seq
# - Mede RTT
# - Retransmite em caso de timeout
import base64
import os

import socket
import json
import time

# Ajustar este IP para o IP do servidor visto de dentro do Mininet.
# Em laboratório simples, vamos começar assumindo que o servidor
# está em 10.0.0.1 (por ex: h1 mesmo, em outro terminal),
# e depois você pode adaptar para o host da VM.
SERVER_IP = "10.0.0.1"
SERVER_PORT = 4433

TIMEOUT = 1.0       # timeout para esperar ACK
MAX_RETRIES = 3     # retransmissões por pacote
NUM_DATA_PKTS = 5   # quantos pacotes de dados enviar

FILE_TO_SEND = "teste_sdn.txt"  # ajuste para o arquivo que você quiser
CHUNK_SIZE = 1024                   # bytes por chunk

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(TIMEOUT)


def send_and_wait_ack(pkt, server_addr):
    """
    Envia um pacote (com campo seq), aguarda ACK com timeout
    e retransmite até MAX_RETRIES.
    Retorna (ok, rtt) onde rtt é o RTT medido ou None se falhou.
    """
    seq = pkt["seq"]
    attempts = 0

    while attempts < MAX_RETRIES:
        attempts += 1
        send_time = time.time()
        sock.sendto(json.dumps(pkt).encode(), server_addr)
        print(f"[SEND] seq={seq}, tentativa={attempts}")

        try:
            data, _ = sock.recvfrom(2048)
            recv_time = time.time()
            rtt = recv_time - send_time

            resp = json.loads(data.decode())
            if resp.get("type") == "ack" and resp.get("seq") == seq:
                print(f"[ACK OK] seq={seq}, rtt={rtt:.3f}s, resp={resp}")
                return True, rtt
            else:
                print(f"[ACK INVÁLIDO] resp={resp}")
        except socket.timeout:
            print(f"[TIMEOUT] seq={seq} (tentativa {attempts})")

    print(f"[FALHA] seq={seq} sem ACK após {MAX_RETRIES} tentativas")
    return False, None

def load_file_chunks(filename, chunk_size=1024):
    """Lê o arquivo em binário e retorna lista de chunks (bytes)."""
    with open(filename, "rb") as f:
        data = f.read()

    chunks = [
        data[i:i + chunk_size]
        for i in range(0, len(data), chunk_size)
    ]
    return chunks


def main():
    server_addr = (SERVER_IP, SERVER_PORT)

    # Handshake
    seq = 0
    handshake = {
        "type": "handshake",
        "seq": seq,
        "msg": "hello-quic-sim"
    }

    print("[CLIENTE] Enviando handshake...")
    ok, rtt = send_and_wait_ack(handshake, server_addr)
    if not ok:
        print("[CLIENTE] Handshake falhou, encerrando.")
        return
    
    # --- ENVIO DE ARQUIVO (NOVO) ---
    if not os.path.exists(FILE_TO_SEND):
        print(f"[CLIENTE] Arquivo {FILE_TO_SEND} não encontrado, pulando envio de arquivo.")
        return

    chunks = load_file_chunks(FILE_TO_SEND, CHUNK_SIZE)
    total = len(chunks)
    print(f"[CLIENTE] Enviando arquivo {FILE_TO_SEND} em {total} chunks de até {CHUNK_SIZE} bytes.")

    seq_base = 1000  # só para separar da sequência dos outros pacotes

    for i, raw_chunk in enumerate(chunks):
        seq = seq_base + i
        b64_chunk = base64.b64encode(raw_chunk).decode()

        pkt = {
            "type": "file_chunk",
            "seq": seq,
            "total": total,
            "filename": os.path.basename(FILE_TO_SEND),
            "data": b64_chunk,
        }

        ok, rtt = send_and_wait_ack(pkt, server_addr)
        if not ok:
            print(f"[CLIENTE] Falha ao enviar chunk seq={seq}. Encerrando transmissão de arquivo.")
            break

    print("[CLIENTE] Fim da transmissão do arquivo.")

    # Envio de pacotes de dados
    for i in range(1, NUM_DATA_PKTS + 1):
        pkt = {
            "type": "data",
            "seq": i,
            "msg": f"pacote_data_{i}"
        }
        ok, rtt = send_and_wait_ack(pkt, server_addr)
        time.sleep(0.5)

    print("[CLIENTE] Fim da simulação QUIC-sim.")

if __name__ == "__main__":
    main()
