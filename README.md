# Radxa Serial Logger & Flasher

Sistema Docker para Radxa Zero 3 que monitora portas seriais DAP (NXP) com interface web e permite gravação remota de firmware via pyocd.

## Funcionalidades

### Logger
- **Autodiscovery**: Detecta automaticamente dispositivos DAP (NXP DAPLink) conectados via USB.
- **Logging Persistente**: Registra logs em arquivos diários com rotação automática no SD externo.
- **Interface Web**: Visualização em tempo real via WebSocket com suporte a cores ANSI.
- **Histórico**: Busca e filtragem de logs por data/hora e texto.
- **Alta velocidade**: Leitura otimizada a 3 Mbps sem perda de dados.

### Flasher
- **Upload remoto**: Envie um arquivo `.hex` pelo navegador e grave no dispositivo.
- **pyocd integrado**: Grava firmware via CMSIS-DAP (DAPLink) usando pyocd dentro do container.
- **Flash individual ou em lote**: Grave um dispositivo por vez ou todos de uma vez.
- **Pausa automática da serial**: A leitura serial é pausada durante o flash para evitar conflito USB.
- **Pack files**: Suporta packs do SiliconLabs (`.pack`) para definição de targets.

---

## Estrutura do Projeto

```
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py              # FastAPI: endpoints REST, WebSocket e Flash
│       ├── serial_manager.py    # Gerenciamento de portas seriais + pause/resume
│       ├── flash_manager.py     # Lógica de gravação via pyocd
│       └── static/
│           └── index.html       # Frontend (Logger + Flasher)
├── packs/                       # Pack files do SiliconLabs (.pack)
├── docker-compose.yml
├── serial-logger.service        # Systemd unit para auto-start
└── README.md
```

---

## Instalação na Radxa

### Pre-requisitos
- Radxa Zero 3 com Linux (Debian/Ubuntu)
- Docker e Docker Compose instalados
- SD externo montado em `/mnt/external_sd`

```bash
# Instalar Docker (se necessário)
sudo apt update && sudo apt install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER
# Faça logout e login novamente
```

### 1. Clonar o repositório

```bash
ssh serial@10.8.162.150
git clone https://github.com/urielcontardi/radxa-datalogger.git ~/serial-logger
cd ~/serial-logger
```

### 2. Preparar o SD externo

```bash
# Criar diretórios para logs e packs
sudo mkdir -p /mnt/external_sd/logs /mnt/external_sd/packs

# Copiar pack files para o SD
sudo cp ~/serial-logger/packs/*.pack /mnt/external_sd/packs/

# Garantir permissões
sudo chown -R $USER:$USER /mnt/external_sd/logs /mnt/external_sd/packs
```

### 3. Subir o Docker

```bash
docker compose up -d --build
```

> O primeiro build demora mais por causa do pyocd e dependências USB.

### 4. Configurar início automático (boot)

```bash
sudo cp ~/serial-logger/serial-logger.service /etc/systemd/system/
sudo sed -i "s|/opt/serial-logger|/home/serial/serial-logger|g" /etc/systemd/system/serial-logger.service
sudo systemctl daemon-reload
sudo systemctl enable serial-logger
sudo systemctl start serial-logger
```

---

## Como Usar

### Acesso Web

Abra no navegador:

```
http://10.8.162.150:8080
```

A interface tem duas abas no topo:

| Aba | Função |
|-----|--------|
| **Logger** | Visualizar logs em tempo real ou histórico, filtrar por data/hora, buscar texto |
| **Flasher** | Selecionar dispositivo, fazer upload de `.hex` e gravar firmware |

### Logger

1. Selecione a porta DAP na aba de dispositivos.
2. Use **Ao Vivo** para ver os logs em tempo real.
3. Use **Carregar** para filtrar por período (data/hora).
4. Use **Buscar** para filtrar por texto.

### Flasher

1. Clique em **Flasher** no topo.
2. Selecione o dispositivo DAP na lista.
3. Faça upload do arquivo `.hex` (arraste ou clique).
4. Clique em **Gravar Firmware** (individual) ou **Gravar em TODOS**.
5. Acompanhe a saída no console.

> **Pack files**: Os `.pack` do SiliconLabs devem estar em `/mnt/external_sd/packs/`.
> Se precisar de um pack diferente, faça upload pela interface (Opções avançadas).

---

## Atualização

Para atualizar o sistema após mudanças no repositório:

```bash
ssh serial@10.8.162.150
cd ~/serial-logger
git pull
docker compose up -d --build
```

Se os packs foram atualizados:
```bash
sudo cp ~/serial-logger/packs/*.pack /mnt/external_sd/packs/
```

---

## Configuração

Variáveis de ambiente configuráveis no `docker-compose.yml`:

| Variável | Default | Descrição |
|----------|---------|-----------|
| `BAUD_RATE` | `3000000` | Baud rate das portas seriais |
| `LOG_DIR` | `/app/logs` | Diretório de logs dentro do container |
| `PACK_DIR` | `/app/packs` | Diretório de pack files dentro do container |
| `PYOCD_TARGET` | `EFR32FG28B322F1024IM48` | Target padrão para pyocd |
| `PYOCD_FREQ` | `20M` | Frequência de flash padrão |

---

## Localização dos Dados

| Dado | Caminho na Radxa |
|------|-------------------|
| Logs seriais | `/mnt/external_sd/logs/<port_id>/<YYYY-MM-DD>.log` |
| Pack files | `/mnt/external_sd/packs/*.pack` |
| Projeto | `~/serial-logger/` |

---

## Comandos Úteis

```bash
# Ver status do container
docker ps

# Ver logs do backend em tempo real
docker compose logs -f serial-logger

# Reiniciar o sistema
docker compose restart

# Rebuildar após mudanças
docker compose up -d --build

# Ver espaço em disco
df -h /mnt/external_sd

# Ver status do serviço systemd
sudo systemctl status serial-logger
```
