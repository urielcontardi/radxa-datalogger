import re
import os
from datetime import datetime, timedelta
from pathlib import Path

# Configuração: ajuste de horas (ex: UTC para Brasília é -3)
HOURS_ADJUST = -3 
LOG_BASE_DIR = Path("/mnt/external_sd/logs")

def adjust_line(line):
    # Regex para encontrar o timestamp: [2026-02-19T04:56:00.677]
    # Aceita tanto T quanto espaço como separador
    match = re.match(r'^\[(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}\.\d{3})\](.*)', line)
    if match:
        ts_str, rest = match.groups()
        try:
            # Normaliza para ISO (com T) para o datetime
            ts_iso = ts_str.replace(' ', 'T')
            dt = datetime.fromisoformat(ts_iso)
            dt_new = dt + timedelta(hours=HOURS_ADJUST)
            
            # Mantém o formato original (se era espaço, mantém espaço)
            sep = ' ' if ' ' in ts_str else 'T'
            new_ts = dt_new.isoformat(timespec='milliseconds').replace('T', sep)
            
            return f"[{new_ts}]{rest}\n"
        except ValueError:
            return line + "\n"
    return line + "\n"

def process_file(file_path):
    print(f"Processando: {file_path}")
    try:
        # Lê o conteúdo
        content = file_path.read_text(encoding='utf-8', errors='replace')
        lines = content.splitlines()
        
        # Ajusta as linhas
        new_lines = [adjust_line(l) for l in lines]
        
        # Cria backup
        backup_path = file_path.with_suffix('.log.bak')
        file_path.rename(backup_path)
        print(f"  Backup criado: {backup_path.name}")
        
        # Escreve o novo arquivo
        file_path.write_text("".join(new_lines), encoding='utf-8')
        print(f"  Arquivo atualizado com sucesso.")
    except Exception as e:
        print(f"  Erro ao processar {file_path.name}: {e}")

if __name__ == "__main__":
    if not LOG_BASE_DIR.exists():
        print(f"Erro: Diretorio {LOG_BASE_DIR} nao encontrado!")
        exit(1)

    log_files = list(LOG_BASE_DIR.glob("**/*.log"))
    if not log_files:
        print("Nenhum arquivo .log encontrado.")
        exit(0)

    print(f"Encontrados {len(log_files)} arquivos. Iniciando ajuste de {HOURS_ADJUST} horas...")
    
    for log_file in log_files:
        # Pula arquivos que já são backups
        if log_file.suffix == '.bak':
            continue
        process_file(log_file)

    print("\nConcluido!")
