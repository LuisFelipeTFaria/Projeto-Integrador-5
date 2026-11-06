import time

from kivy.metrics import dp
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput
from kivy.uix.gridlayout import GridLayout
from kivymd.app import MDApp
from kivymd.uix.screenmanager import MDScreenManager
from kivymd.uix.screen import MDScreen
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.button import MDRaisedButton, MDIconButton
from kivymd.uix.slider import MDSlider
from kivymd.uix.tab import MDTabs, MDTabsBase
from kivymd.uix.textfield import MDTextField
from kivymd.uix.gridlayout import MDGridLayout
from random import randint
# =========================================================
# Importação segura Pyjnius + permissões Android
# =========================================================
try:
    from jnius import autoclass
    from android.permissions import request_permissions, Permission

    BluetoothAdapter = autoclass('android.bluetooth.BluetoothAdapter')
    UUID = autoclass('java.util.UUID')

    ANDROID = True
except Exception as e:
    print("⚠ Bluetooth desativado ou Pyjnius não disponível:", e)
    BluetoothAdapter = None
    ANDROID = False


# =========================================================
# GERENCIADOR BLUETOOTH
# =========================================================
class BluetoothManager:
    def __init__(self):
        self.adapter = BluetoothAdapter.getDefaultAdapter() if ANDROID else None
        self.socket = None
        self.device = None
        self.uuid = None
        if ANDROID and self.adapter:
            self.uuid = UUID.fromString("00001101-0000-1000-8000-00805f9b34fb")

    def conectar(self, endereco):
        """Conecta ao dispositivo Bluetooth pelo MAC address."""
        try:
            device = self.adapter.getRemoteDevice(endereco)
            socket = device.createRfcommSocketToServiceRecord(self.uuid)
            self.adapter.cancelDiscovery()
            print(f"Tentando conectar a {device.getName()} ({endereco})...")
            socket.connect()
            self.socket = socket
            self.device = device
            print(f"Conectado a {device.getName()} ({device.getAddress()})")
            return True
        except Exception as e:
            print("Erro ao conectar:", e)
            self.socket = None
            return False

    def enviar(self, texto):
        """Envia uma string terminada com ';' ao ESP."""
        if self.socket:
            try:
                output = self.socket.getOutputStream()
                output.write((texto + ";").encode())
                output.flush()
                print(f"-> Enviado: {texto}")
            except Exception as e:
                print("Erro ao enviar:", e)
        else:
            print("Nenhum dispositivo conectado.")

    def receber(self):
        """Lê dados recebidos do ESP."""
        if not self.socket:
            return None
        try:
            input_stream = self.socket.getInputStream()
            available = input_stream.available()
            if available > 0:
                data = bytearray()
                for _ in range(available):
                    data.append(input_stream.read())
                msg = data.decode(errors="ignore").strip()
                if msg:
                    print(f"<- Recebido: {msg}")
                    return msg
        except Exception as e:
            print("Erro ao receber:", e)
        return None

    def desconectar(self):
        """Desconecta e fecha o socket Bluetooth."""
        if self.socket:
            try:
                self.socket.close()
                print("🔌 Desconectado.")
            except Exception as e:
                print("Erro ao desconectar:", e)
        self.socket = None
        self.device = None


# =========================================================
# ABA CONTROLE
# =========================================================
class AbaControle(MDBoxLayout, MDTabsBase):
    def __init__(self, bt_manager, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(15), padding=dp(20), **kwargs)
        self.bt_manager = bt_manager

        # Título
        self.add_widget(MDLabel(text="Controle do Robô", halign="center", font_style="H5"))

        # -------------------------
        # Slider de velocidade
        # -------------------------
        self.vel_label = MDLabel(text="Velocidade: 120", halign="center")
        self.slider = MDSlider(min=0, max=255, value=120)
        self.slider.bind(value=self.on_slider_change)
        self.add_widget(self.vel_label)
        self.add_widget(self.slider)

        # -------------------------
        # Botão de controle do motor
        # -------------------------
        self.toggle_btn = MDRaisedButton(
            text="Ligar",
            size_hint_y=None,
            height=dp(50)
        )
        self.toggle_btn.bind(on_release=self.toggle_motor)
        self.add_widget(self.toggle_btn)

        # =========================================================
        # NOVAS OPÇÕES: Ângulo e Distância
        # =========================================================

        # Campo e botão para ângulo objetivo
        angulo_layout = MDBoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(50))
        self.angulo_input = MDTextField(
            hint_text="Ângulo objetivo",
            input_filter="int",
            mode="rectangle"
        )
        self.btn_enviar_angulo = MDRaisedButton(
            text="Enviar ângulo",
            size_hint_x=None,
            width=dp(140)
        )
        self.btn_enviar_angulo.bind(on_release=self.enviar_angulo)
        angulo_layout.add_widget(self.angulo_input)
        angulo_layout.add_widget(self.btn_enviar_angulo)
        self.add_widget(angulo_layout)

        # Campo e botão para distância para virar
        distancia_layout = MDBoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(50))
        self.distancia_input = MDTextField(
            hint_text="Distância para virar",
            input_filter="int",
            mode="rectangle"
        )
        self.btn_enviar_distancia = MDRaisedButton(
            text="Enviar distância",
            size_hint_x=None,
            width=dp(140)
        )
        self.btn_enviar_distancia.bind(on_release=self.enviar_distancia)
        distancia_layout.add_widget(self.distancia_input)
        distancia_layout.add_widget(self.btn_enviar_distancia)
        self.add_widget(distancia_layout)

    def on_slider_change(self, instance, value):
        v = int(value)
        self.vel_label.text = f"Velocidade: {v}"
        self.bt_manager.enviar(f"velocidade:{v}")

    def toggle_motor(self, instance):
        if instance.text == "Ligar":
            instance.text = "Desligar"
            self.bt_manager.enviar("motor:on")
        else:
            instance.text = "Ligar"
            self.bt_manager.enviar("motor:off")

    # =========================================================
    # NOVOS MÉTODOS
    # =========================================================
    def enviar_angulo(self, instance):
        valor = self.angulo_input.text.strip()
        if valor.isdigit():
            self.bt_manager.enviar(f"anguloObjetivo:{valor}")
        else:
            print("Valor inválido para ângulo objetivo.")

    def enviar_distancia(self, instance):
        valor = self.distancia_input.text.strip()
        if valor.isdigit():
            self.bt_manager.enviar(f"distanciaParaVirar:{valor}")
        else:
            print("Valor inválido para distância para virar.")


class AbaControleRemoto(MDBoxLayout, MDTabsBase):
    def __init__(self, bt_manager, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(20), padding=dp(20), **kwargs)
        self.bt_manager = bt_manager
        self.modo_ativo = False

        # Título
        self.add_widget(MDLabel(
            text="Controle Remoto",
            halign="center",
            font_style="H5"
        ))

        # Botão para ligar/desligar o modo remoto
        self.toggle_modo = MDRaisedButton(
            text="Ativar Modo Remoto",
            size_hint_y=None,
            height=dp(50)
        )
        self.toggle_modo.bind(on_release=self.toggle_modo_remoto)
        self.add_widget(self.toggle_modo)

        # --- Layout dos botões estilo joystick ---
        grid = GridLayout(cols=3, spacing=dp(15), size_hint=(None, None))
        grid.size = (dp(300), dp(300))
        grid.pos_hint = {"center_x": 0.5}

        # Cima
        grid.add_widget(MDLabel())
        grid.add_widget(self.criar_botao("arrow-up-bold", "passoFrente:1"))
        grid.add_widget(MDLabel())

        # Esquerda / Parar / Direita
        grid.add_widget(self.criar_botao("arrow-left-bold", "passoEsquerda:1"))
        grid.add_widget(self.criar_botao("stop-circle-outline", "parar:1", cor=(1, 0, 0, 1), fundo=(0.1, 0.1, 0.1, 1)))
        grid.add_widget(self.criar_botao("arrow-right-bold", "passoDireita:1"))

        # Baixo
        grid.add_widget(MDLabel())
        grid.add_widget(self.criar_botao("arrow-down-bold", "passoTras:1"))
        grid.add_widget(MDLabel())

        self.add_widget(grid)

    # Função utilitária para criar botões
    def criar_botao(self, icone, comando, cor=(1, 1, 1, 1), fundo=(0.2, 0.4, 0.8, 1)):
        btn = MDIconButton(
            icon=icone,
            icon_size=dp(64),
            size_hint=(None, None),
            size=(dp(100), dp(100)),
            md_bg_color=fundo,
            icon_color=cor,
            pos_hint={"center_x": 0.5, "center_y": 0.5},
            on_release=lambda x: self.enviar_direcao(comando)
        )
        return btn

    def toggle_modo_remoto(self, instance):
        self.modo_ativo = not self.modo_ativo
        if self.modo_ativo:
            instance.text = "Desativar Modo Remoto"
            self.bt_manager.enviar("controle_remoto:on")
        else:
            instance.text = "Ativar Modo Remoto"
            self.bt_manager.enviar("andarAutonomo:0")

    def enviar_direcao(self, comando):
        if not self.modo_ativo:
            print("⚠ Ative o modo remoto primeiro!")
            return
        self.bt_manager.enviar(comando)
        print(f"Direção enviada: {comando}")

# =========================================================
# ABA BLUETOOTH
# =========================================================
class AbaBluetooth(MDBoxLayout, MDTabsBase):
    def __init__(self, bt_manager, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(10), padding=dp(10), **kwargs)
        self.bt_manager = bt_manager

        status_box = MDBoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(50))
        self.status_label = MDLabel(text="Status: Desconectado", halign="left", font_style="H6")
        self.connect_btn = MDRaisedButton(text="Conectar ao ESP", size_hint_x=None, width=dp(160))
        self.connect_btn.bind(on_release=self.tentar_conectar)
        status_box.add_widget(self.status_label)
        status_box.add_widget(self.connect_btn)
        self.add_widget(status_box)

        self.text_field = MDTextField(hint_text="Digite um comando...", size_hint_y=None, height=dp(50))
        self.add_widget(self.text_field)

        self.scroll = ScrollView(size_hint=(1, 1))
        self.terminal = TextInput(
            readonly=True,
            font_size=30,
            size_hint_y=None,
            height=dp(300),
            background_color=(0, 0, 0, 1),
            foreground_color=(0, 1, 0, 1),
        )
        self.scroll.add_widget(self.terminal)
        self.add_widget(self.scroll)

        self.send_btn = MDRaisedButton(text="Enviar", size_hint_y=None, height=dp(50))
        self.send_btn.bind(on_release=self.enviar_texto)
        self.add_widget(self.send_btn)

        self.update_event = None

    def tentar_conectar(self, instance):
        endereco_esp = "7C:9E:BD:F2:E1:C6"
        if self.bt_manager.conectar(endereco_esp):
            self.status_label.text = "Conectado ao ESP"
            self.connect_btn.text = "Desconectar"
            self.connect_btn.unbind(on_release=self.tentar_conectar)
            self.connect_btn.bind(on_release=self.desconectar)
            self.update_event = Clock.schedule_interval(self.ler_dados, 0.5)
            self.terminal.text += "\nConectado com sucesso!"
        else:
            self.status_label.text = "Falha ao conectar"
            self.terminal.text += "\nErro ao tentar conectar."

    def desconectar(self, instance):
        if self.update_event:
            self.update_event.cancel()
        self.bt_manager.desconectar()
        self.status_label.text = "Status: Desconectado"
        self.connect_btn.text = "Conectar ao ESP"
        self.connect_btn.unbind(on_release=self.desconectar)
        self.connect_btn.bind(on_release=self.tentar_conectar)
        self.terminal.text += "\nDesconectado."

    def enviar_texto(self, instance):
        texto = self.text_field.text.strip()
        if texto:
            self.bt_manager.enviar(texto)
            self.terminal.text += f"\n-> {texto}"
            self.text_field.text = ""
            self.scroll.scroll_y = 0

    def ler_dados(self, dt):
        msg = self.bt_manager.receber()
        if msg:
            self.terminal.text += f"\n<- {msg}"
            self.scroll.scroll_y = 0


# =========================================================
# ABA MAPA
# =========================================================
class AbaMapa(MDBoxLayout, MDTabsBase):
    def __init__(self, bt_manager=None, **kwargs):
        super().__init__(orientation="vertical", spacing=dp(10), padding=dp(10), **kwargs)
        self.bt_manager = bt_manager
        self.tamanho = 10
        self.matriz = [[0 for _ in range(self.tamanho)] for _ in range(self.tamanho)]

        self.add_widget(MDLabel(text="Mapa de Navegação", halign="center", font_style="H5"))
        self.grid = GridLayout(cols=self.tamanho, rows=self.tamanho, size_hint=(None, None),
                               width=dp(300), height=dp(300), spacing=dp(1))
        self.grid.pos_hint = {"center_x": 0.5}
        self.celulas = []

        for i in range(self.tamanho):
            linha = []
            for j in range(self.tamanho):
                cor = self._cor_por_valor(self.matriz[i][j])
                celula = MDBoxLayout(md_bg_color=cor, size_hint=(None, None), size=(dp(28), dp(28)))
                linha.append(celula)
                self.grid.add_widget(celula)
            self.celulas.append(linha)
        self.add_widget(self.grid)

        simular_btn = MDRaisedButton(text="Simular Recepção de Dados", size_hint_y=None, height=dp(50))
        simular_btn.bind(on_release=self.simular_recebimento)
        self.add_widget(simular_btn)

        legenda = MDBoxLayout(orientation="horizontal", spacing=dp(10), size_hint_y=None, height=dp(50))
        legenda.add_widget(self._bloco_legenda("Desconhecido", (0, 0, 0, 1)))
        legenda.add_widget(self._bloco_legenda("Livre", (0, 1, 0, 1)))
        legenda.add_widget(self._bloco_legenda("Obstáculo", (1, 0, 0, 1)))
        legenda.add_widget(self._bloco_legenda("Fronteira", (1, 1, 0, 1)))
        self.add_widget(legenda)

        # Atualização periódica
        if self.bt_manager:
            Clock.schedule_interval(self.verificar_bluetooth, 0.5)

    # =========================================================
    # Processamento dos dados recebidos
    # =========================================================
    def verificar_bluetooth(self, dt):
        msg = self.bt_manager.receber()
        if msg:
            self.terminal.text += f"\n<- {msg}"
            self.scroll.scroll_y = 0
            # Verifica se a mensagem tem o cabeçalho "MPA"
            if msg.startswith("MPA"):
                self.processar_mpa(msg)
            else:
                print(f"⚠ Mensagem desconhecida: {msg}")

    def processar_mpa(self, dados):
        # O formato esperado é: MPAXXXX;YYYY;VV
        partes = dados[3:].split(";")  # Ignora 'MPA' e divide pelos ';'
        if len(partes) == 3:
            x = int(partes[0], 2)  # Primeiros 4 bits (X)
            y = int(partes[1], 2)  # Próximos 4 bits (Y)
            valor = int(partes[2], 2)  # Valor da cor (2 bits)

            # Atualiza a célula no mapa com as coordenadas e valor de cor
            self._atualizar_mapa(x, y, valor)

            print(f"🟩 MAPA atualizado: X={x} Y={y} Valor={valor}")
        else:
            print(f"⚠ Formato de dados inválido para MPA: {dados}")

    def _atualizar_mapa(self, x, y, v):
        """Função auxiliar que realmente atualiza o mapa visual"""
        if 0 <= x < self.tamanho and 0 <= y < self.tamanho:
            self.matriz[y][x] = v
            self.celulas[y][x].md_bg_color = self._cor_por_valor(v)
        else:
            print(f"⚠ Coordenadas fora do limite: ({x}, {y})")

    def _cor_por_valor(self, v):
        if v == 0:
            return (0, 0, 0, 1)       # desconhecido
        elif v == 1:
            return (0, 1, 0, 1)       # livre
        elif v == 2:
            return (1, 0, 0, 1)       # obstáculo
        elif v == 3:
            return (1, 1, 0, 1)   # fronteira
        return (1, 1, 1, 1)           # fallback

    def simular_recebimento(self, instance):
        print("\n--- Simulação de recebimento múltiplo iniciada ---")
        # Número de mensagens simuladas
        for _ in range(20):  # Envia 20 pacotes
            # Gera coordenadas X e Y aleatórias no intervalo de 0 a 9 (4 bits)
            x = randint(0, 9)
            y = randint(0, 9)

            # Gera valor aleatório para a cor (1, 2 ou 3)
            v = randint(1, 3)

            # Converte coordenadas X e Y para binário de 4 bits
            x_bin = f"{x:04b}"  # Converte X para binário com 4 bits
            y_bin = f"{y:04b}"  # Converte Y para binário com 4 bits

            # Converte o valor da célula (v) para binário de 2 bits
            v_bin = f"{v:02b}"  # Converte v para binário com 2 bits

            # Cria a mensagem no formato correto (MPA + coordenadas binárias + valor binário)
            msg = f"MPA{x_bin};{y_bin};{v_bin}"

            print(f"Recebendo: {msg}")
            self.processar_mpa(msg)  # Processa a mensagem
            time.sleep(0.1)
        print("--- Simulação concluída ---\n")

    def _bloco_legenda(self, texto, cor):
        box = MDBoxLayout(orientation="horizontal", spacing=dp(5), size_hint_x=None, width=dp(120))
        quadrado = MDBoxLayout(md_bg_color=cor, size_hint=(None, None), size=(dp(20), dp(20)))
        label = MDLabel(text=texto, halign="left")
        box.add_widget(quadrado)
        box.add_widget(label)
        return box

# =========================================================
# TELA PRINCIPAL
# =========================================================
class TelaPrincipal(MDScreen):
    def __init__(self, bt_manager, **kwargs):
        super().__init__(**kwargs)
        tabs = MDTabs()
        tabs.add_widget(AbaControle(bt_manager, title="Controle"))
        tabs.add_widget(AbaBluetooth(bt_manager, title="Terminal"))
        tabs.add_widget(AbaMapa(title="Mapa"))
        tabs.add_widget(AbaControleRemoto(bt_manager, title="Controle Remoto"))  # 🔹 NOVA ABA
        self.add_widget(tabs)


# =========================================================
# APP PRINCIPAL
# =========================================================
class AppRoboAspirador(MDApp):
    def build(self):
        Window.clearcolor = (0.9, 0.9, 0.9, 1)

        if ANDROID:
            request_permissions([
                Permission.BLUETOOTH,
                Permission.BLUETOOTH_ADMIN,
                Permission.BLUETOOTH_CONNECT,
                Permission.BLUETOOTH_SCAN,
                Permission.ACCESS_FINE_LOCATION,
                Permission.ACCESS_COARSE_LOCATION
            ])

        self.bt_manager = BluetoothManager()
        sm = MDScreenManager()
        sm.add_widget(TelaPrincipal(name="principal", bt_manager=self.bt_manager))
        return sm


if __name__ == "__main__":
    AppRoboAspirador().run()
