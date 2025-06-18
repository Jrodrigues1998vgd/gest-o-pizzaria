import os
import sys
import subprocess
import webbrowser
import time

def main():
    # Encontra o caminho do script principal
    # Verifique se o nome "sistema gestão.py" está correto
    script_path = os.path.join(os.path.dirname(__file__), "sistema gestão.py")

    # Comando para iniciar o Streamlit
    command = f'"{sys.executable}" -m streamlit run "{script_path}" --server.port 8501 --server.headless "true"'

    print("Iniciando o GMaster... Por favor, aguarde.")
    
    # Inicia o processo do Streamlit
    subprocess.Popen(command, shell=True)
    
    # Espera um pouco para o servidor iniciar e abre o navegador
    time.sleep(5)
    webbrowser.open("http://localhost:8501", new=2, autoraise=True)

if __name__ == "__main__":
    main()