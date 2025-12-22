# 📘 **TRABALHO FINAL — Redes e Computação em Nuvem**

## **Controle de Fluxos QUIC-sim e Transferência de Arquivos via SDN em Topologia com 4 Roteadores**

### **Trabalho em Equipe (até 4 integrantes)**

---

# 1. Objetivos do Trabalho Final

Este trabalho integra os pilares da disciplina:

* Virtualização e experimentação com Mininet
* Open vSwitch como plano de dados
* SDN com Ryu (OpenFlow 1.3)
* Engenharia de tráfego
* Protocolos modernos baseados em UDP (QUIC-sim)
* Coleta de métricas de desempenho
* Avaliação de segurança em redes programáveis

A tarefa principal da equipe é construir um ambiente de experimentação completo no qual:

1. O protocolo **QUIC-sim** realiza:

   * handshake
   * envio confiável de mensagens
   * transmissão completa de **um arquivo real**, dividido em chunks, com ACK por chunk
   * retransmissão em caso de timeout
   * medição de RTT por chunk

2. O tráfego QUIC-sim (UDP/4433) é **controlado pelo SDN** em uma topologia mesh com 4 switches OVS usando Ryu.

3. A equipe executa uma série de experimentos (rotas diferentes, ECMP-sim, falhas de link, políticas de segurança) e **coleta dados quantitativos** para compor o relatório.

---

# 2. Trabalho em Equipe – Regras

* Equipes de **1 a 4 alunos**.
* Um único relatório por equipe.
* É obrigatória a seção **Participação Individual dos Integrantes**, descrevendo:

  * contribuições técnicas
  * trechos de código escritos
  * experimentos conduzidos


---

# 3. Topologia Oficial — Malha com 4 Roteadores

A topologia obrigatória é:

```
        s1 -------- s2
        |            |
        |            |
        s3 -------- s4
```

Hosts:

```
h1 conectado a s1 (servidor QUIC-sim)
h2 conectado a s4 (cliente QUIC-sim)
```

Esta topologia fornece **múltiplos caminhos** entre cliente e servidor:

* Caminho superior: s1 → s2 → s4
* Caminho inferior: s1 → s3 → s4
* ECMP-sim: alternância dinâmica
* Cenários de reroteamento sob falhas

O arquivo **`topo_malha.py`** será fornecido.

---

# 4. Protocolo QUIC-sim com Envio de Arquivo

A equipe utilizará o protocolo QUIC-sim fornecido:

* `udp_server_final.py`
* `udp_client_final.py`

Agora expandido com a capacidade de:

### ✔ Enviar **um arquivo real** do cliente para o servidor

### ✔ Dividir o arquivo em chunks (ex.: 1024 bytes)

### ✔ Codificar cada chunk em base64

### ✔ Enviar cada chunk com campos:

```json
{
  "type": "file_chunk",
  "seq": 1020,
  "total": 57,
  "data": "<base64>"
}
```

### ✔ Receber ACK por chunk:

```json
{ "type": "ack_chunk", "seq": 1020 }
```

### ✔ Retransmitir chunks não confirmados

### ✔ Reconstituir o arquivo no servidor e verificar integridade (MD5/SHA-1)

O arquivo a ser enviado pode ser qualquer texto, imagem pequena ou dataset simples de 20 KB a 500 KB.

---

# 5. Execução do Ambiente

O trabalho deve ser conduzido usando **processos em background (`&`)**.

---

## 5.1. Executar o Controlador SDN

Em um terminal:

```bash
cd ~/lab-quic-sdn
ryu-manager simple_switch_final.py
```

Mantenha este terminal aberto para visualizar logs.

---

## 5.2. Executar o Mininet com topologia mesh

Em outro terminal:

```bash
sudo mn --custom topo_malha.py --topo mesh4 \
        --controller=remote --switch ovsk --mac
```

Verifique IPs de h1 e h2:

```bash
mininet> h1 ip a
mininet> h2 ip a
```

---

## 5.3. Executar QUIC-sim com processos em background

### Servidor (em h1):

```bash
mininet> h1 python3 udp_quic_server.py &
```

### Cliente (em h2) para enviar arquivo:

```bash
mininet> h2 python3 udp_quic_client.py
```

### Verificar processos:

```bash
mininet> h1 ps -ef | grep python
```

### Encerrar servidor:

```bash
mininet> h1 kill %python3
```

---

# 6. Manipulação SDN – Experimentos Obrigatórios

Cada equipe deve implementar **todas** as manipulações abaixo no arquivo `simple_switch_final.py`.

(As instruções detalhadas sobre como manipular flows, matches e prioridades estão no enunciado completo acima e dentro dos slides da disciplina.)

---

## ✔ Experimento 1 — Baseline (sem regras específicas)

Coletar:

* RTT médio por chunk
* taxa de retransmissão
* throughput (arquivo/tempo)
* fluxos instalados automaticamente

---

## ✔ Experimento 2 — Rota Superior Forçada

Modificar controlador para que QUIC-sim siga:

```
h1 → s1 → s2 → s4 → h2
```

Coletar métricas e comparar com baseline.

---

## ✔ Experimento 3 — Rota Inferior Forçada

Controlador deve forçar:

```
h1 → s1 → s3 → s4 → h2
```

Comparar:

* RTT médio
* jitter
* retransmissões

---

## ✔ Experimento 4 — ECMP-sim (balanceamento)

O controlador deve alternar dinamicamente entre os caminhos:

```python
actions = [parser.OFPActionOutput(random.choice([porta_s2, porta_s3]))]
```

Avaliar:

* instabilidade
* jitter
* perda

---

## ✔ Experimento 5 — Falha de Link + Recuperação

Simular:

```bash
mininet> link s1 s2 down
```

O controlador deve:

* redirecionar automaticamente via s1 → s3 → s4
* manter a transferência funcional

Registrar:

* tempo de recuperação
* retransmissões adicionais
* diferenças de RTT

---

## ✔ Experimento 6 — Política de Segurança (escolher uma)

Implementar:

* bloquear handshake
* bloquear chunks pares
* degradar caminho
* drop parcial (DoS)
* priorização (priority > 200)

Avaliar impacto no protocolo QUIC-sim e na integridade do arquivo reconstruído.

---

# 7. Métricas Obrigatórias

Para cada experimento:

### ✔ RTT por chunk (gráfico)

### ✔ Retransmissões por chunk

### ✔ Throughput efetivo

### ✔ Tempo total de envio do arquivo

### ✔ Fluxos instalados nos switches

### ✔ Logs do controlador

### ✔ Integridade do arquivo reconstruído (MD5/SHA-1)

---

# 8. Reflexão sobre Segurança

Incluir no relatório:

1. **Como a SDN controla QUIC-sim e controlaria um QUIC real, totalmente criptografado?**
2. **Quais ataques podem ser realizados via SDN?**
3. **Como defender o tráfego com políticas SDN?**
4. **Como caminhos múltiplos afetam segurança e desempenho?**

---

# 9. Entregáveis da Equipe

### ✔ Relatório Final (PDF, 6–12 páginas)

Contendo:

* Introdução
* Descrição da topologia
* Descrição do QUIC-sim e do envio de arquivo
* Modificações no controlador
* Todos os experimentos 1–6
* Gráficos, tabelas, fluxos
* Reflexão de segurança
* Participação Individual

---

### ✔ Código completo

* `simple_switch_final.py`
* Scripts auxiliares da equipe (se houver)

---

### ✔ Evidências

* prints
* dumps de fluxos
* logs do Ryu
* hashes MD5/SHA-1 do arquivo enviado e reconstruído

---

# 10. Rubrica de Avaliação

| Critério                                         | Peso |
| ------------------------------------------------ | ---- |
| Execução da topologia mesh                       | 1.0  |
| Execução correta do QUIC-sim + envio de arquivo  | 2.0  |
| Manipulação SDN (experimentos 1–6)               | 3.0  |
| Métricas e análise de desempenho                 | 2.0  |
| Reflexão de segurança                            | 1.0  |
| Qualidade do relatório + participação individual | 1.0  |

**Total: 10 pontos**


