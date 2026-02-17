# Serial Logger - Radxa Zero 3

Sistema de monitoramento e registro de portas seriais DAP (NXP) com interface web em tempo real.

## 🚀 Funcionalidades

- **Autodiscovery**: Detecta automaticamente dispositivos DAP (NXP) conectados via USB.
- **Logging Persistente**: Registra logs em arquivos diários com rotação automática.
- **Interface Web**: Visualização em tempo real via WebSocket com suporte a cores ANSI.
- **Histórico**: Busca e filtragem de logs por data e texto.
- **Auto-start**: Configuração para iniciar automaticamente no boot do Linux embarcado.

---

## 🛠️ Estrutura do Projeto

- `backend/`: API FastAPI e lógica de gerenciamento serial.
- `logs/`: Pasta onde os arquivos `.log` são armazenados (organizados por ID do dispositivo).
- `docker-compose.yml`: Orquestração dos containers.
- `serial-logger.service`: Arquivo de configuração para o systemd.

---

## 💻 Instalação na Radxa (Linux Embarcado)

### 1. Enviar arquivos para a Radxa
No seu computador local, dentro da pasta do projeto, execute:

```bash
git push origin main
```

Na Radxa:
```bash
ssh serial@10.8.162.150
cd ~/serial-logger
git pull
```

### 2. Iniciar o Docker
Suba os containers:

```bash
docker compose up -d --build
```

### 3. Configurar Início Automático (Boot)
Para que o sistema inicie sozinho ao ligar a Radxa:

```bash
# Copia o arquivo de serviço
sudo cp ~/serial-logger/serial-logger.service /etc/systemd/system/

# Ajusta o caminho da pasta no arquivo de serviço
sudo sed -i "s|/opt/serial-logger|/home/serial/serial-logger|g" /etc/systemd/system/serial-logger.service

# Habilita e inicia o serviço
sudo systemctl daemon-reload
sudo systemctl enable serial-logger
sudo systemctl start serial-logger
```

---

## 📖 Como Usar

### Acesso Web
Acesse pelo navegador:
`http://10.8.162.150:8080`

### Localização dos Logs
Os logs ficam salvos na Radxa no cartão SD externo em:
`/mnt/external_sd/logs/`

### Comandos Úteis de Monitoramento
```bash
# Ver status dos containers
docker ps

# Ver logs do backend em tempo real
docker compose logs -f serial-logger

# Reiniciar o sistema
docker compose restart
```
