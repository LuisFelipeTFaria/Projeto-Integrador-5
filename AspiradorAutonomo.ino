/*
 * AspiradorAutonomo.ino
 *
 * Robô aspirador autônomo no modo "vai e bate" (bump-and-go).
 * Anda em linha reta; ao encontrar obstáculo (ou queda, se houver
 * sensor), para, recua, escolhe um lado e gira por um ângulo medido
 * pelo giroscópio. Funciona sozinho: sem app, sem Bluetooth, sem Wi-Fi.
 *
 * Placa:      Arduino Mega 2560 + shield de motores (4 motores DC)
 * Sensores:   3 x HC-SR04 (frente, esquerda, direita) e 1 x MPU-6050
 * Bibliotecas: AFMotor_R4 (ou AFMotor), MPU6050 e Wire
 *
 * 
 */

#include <Wire.h>
#include <AFMotor_R4.h>   // se a sua biblioteca for a AFMotor.h, troque aqui
#include <MPU6050.h>

// =====================================================================
//  AJUSTES (mexa aqui para calibrar o comportamento do robô)
// =====================================================================
const bool          MODO_DEPURACAO         = false;  // true: mostra dados no USB
const uint8_t       POTENCIA_ANDAR         = 200;    // 0 a 255
const uint8_t       POTENCIA_GIRO          = 190;    // 0 a 255
const float         LIMITE_OBSTACULO_CM    = 25.0;   // distância para reagir
const unsigned long TEMPO_RE_MS            = 450;    // quanto recua
const int           GIRO_MINIMO_GRAUS      = 80;     // sorteio do ângulo
const int           GIRO_MAXIMO_GRAUS      = 140;
const float         ANTECIPACAO_GRAUS      = 8.0;    // para antes (inércia)
const unsigned long LIMITE_TEMPO_GIRO_MS   = 3500;   // segurança do giro
const bool          INVERTER_SENTIDO_GIRO  = false;  // true se o ângulo sair negativo
const bool          M1_M2_NO_LADO_DIREITO  = true;   // veja a nota abaixo
const unsigned long JANELA_PRESO_MS        = 2500;   // detecção de "preso"
const uint8_t       BLOQUEIOS_PARA_RETORNO = 3;      // 3 batidas seguidas: meia-volta

// Sensor de queda (infravermelho reflexivo) - opcional
const bool          SENSOR_QUEDA_ATIVO     = false;
const uint8_t       PINO_QUEDA             = A0;
const uint8_t       NIVEL_DE_QUEDA         = HIGH;   // leitura que significa "sem chão"

// Motor de sucção (via transistor ou relé) - opcional
const bool          SUCCAO_ATIVA           = false;
const uint8_t       PINO_SUCCAO            = 22;



// =====================================================================
//  PINOS DOS SENSORES ULTRASSÔNICOS  [0 = frente, 1 = esquerda, 2 = direita]
// =====================================================================
const uint8_t PINO_DISPARO[3] = {49, 31, 36};
const uint8_t PINO_ECO[3]     = {53, 33, 34};
const uint8_t AMOSTRAS_POR_LEITURA = 3;
const float   DISTANCIA_LONGE_CM   = 400.0;

// =====================================================================
//  ESTADO GLOBAL
// =====================================================================
MPU6050 giroscopio;
float         viesGiroZ         = 0.0;   // erro de zero do giroscópio
float         rumoGraus         = 0.0;   // ângulo acumulado durante o giro
unsigned long instanteAnteriorUs = 0;

unsigned long ultimaReacaoMs   = 0;
uint8_t       batidasSeguidas  = 0;

AF_DCMotor motor1(1), motor2(2), motor3(3), motor4(4);
AF_DCMotor *ladoDireito[2];
AF_DCMotor *ladoEsquerdo[2];

// =====================================================================
//  SENSORES ULTRASSÔNICOS
// =====================================================================
float medirEcoCm(uint8_t s) {
  digitalWrite(PINO_DISPARO[s], LOW);
  delayMicroseconds(3);
  digitalWrite(PINO_DISPARO[s], HIGH);
  delayMicroseconds(10);
  digitalWrite(PINO_DISPARO[s], LOW);

  unsigned long duracaoUs = pulseIn(PINO_ECO[s], HIGH, 25000UL);
  if (duracaoUs == 0) return -1.0;            // sem eco
  return duracaoUs / 58.0;                    // microssegundos -> cm
}

// Mediana de algumas leituras: descarta picos e falhas isoladas.
float ecoMediano(uint8_t s) {
  float validas[AMOSTRAS_POR_LEITURA];
  uint8_t qtd = 0;

  for (uint8_t i = 0; i < AMOSTRAS_POR_LEITURA; i++) {
    float d = medirEcoCm(s);
    if (d > 0) validas[qtd++] = d;
    delay(4);
  }
  if (qtd == 0) return -1.0;

  for (uint8_t i = 1; i < qtd; i++) {         // ordenação por inserção
    float chave = validas[i];
    int8_t j = i - 1;
    while (j >= 0 && validas[j] > chave) {
      validas[j + 1] = validas[j];
      j--;
    }
    validas[j + 1] = chave;
  }
  return validas[qtd / 2];
}

// =====================================================================
//  GIROSCÓPIO (eixo Z)
// =====================================================================
void calibrarGiro() {
  const uint16_t TOTAL = 400;
  long soma = 0;
  for (uint16_t i = 0; i < TOTAL; i++) {
    soma += giroscopio.getRotationZ();
    delay(3);
  }
  viesGiroZ = (float)soma / TOTAL;
}

void integrarGiro() {
  unsigned long agora = micros();
  float dt = (agora - instanteAnteriorUs) / 1000000.0;
  instanteAnteriorUs = agora;

  float graus_por_s = (giroscopio.getRotationZ() - viesGiroZ) / 131.0;
  if (fabs(graus_por_s) < 0.4) graus_por_s = 0;      // zona morta (ruído)
  if (INVERTER_SENTIDO_GIRO) graus_por_s = -graus_por_s;

  rumoGraus += graus_por_s * dt;
}

// =====================================================================
//  MOTORES
// =====================================================================
void mapearLados() {
  if (M1_M2_NO_LADO_DIREITO) {
    ladoDireito[0] = &motor1;  ladoDireito[1] = &motor2;
    ladoEsquerdo[0] = &motor3; ladoEsquerdo[1] = &motor4;
  } else {
    ladoDireito[0] = &motor3;  ladoDireito[1] = &motor4;
    ladoEsquerdo[0] = &motor1; ladoEsquerdo[1] = &motor2;
  }
}

void definirPotencia(uint8_t p) {
  for (uint8_t i = 0; i < 2; i++) {
    ladoDireito[i]->setSpeed(p);
    ladoEsquerdo[i]->setSpeed(p);
  }
}

void moverLados(uint8_t sentidoEsq, uint8_t sentidoDir) {
  for (uint8_t i = 0; i < 2; i++) {
    ladoEsquerdo[i]->run(sentidoEsq);
    ladoDireito[i]->run(sentidoDir);
  }
}

void avancar() {
  definirPotencia(POTENCIA_ANDAR);
  moverLados(FORWARD, FORWARD);
}

void recuar() {
  definirPotencia(POTENCIA_ANDAR);
  moverLados(BACKWARD, BACKWARD);
}

void rotacionar(bool paraEsquerda) {
  definirPotencia(POTENCIA_GIRO);
  if (paraEsquerda) moverLados(BACKWARD, FORWARD);
  else              moverLados(FORWARD, BACKWARD);
}

void pararRobo() {
  moverLados(RELEASE, RELEASE);
}

// =====================================================================
//  SENSOR DE QUEDA (opcional)
// =====================================================================
bool semChaoAFrente() {
  if (!SENSOR_QUEDA_ATIVO) return false;
  return digitalRead(PINO_QUEDA) == NIVEL_DE_QUEDA;
}

// =====================================================================
//  MANOBRAS
// =====================================================================
// Gira até o ângulo pedido, medido pelo giroscópio.
void girarPorGraus(bool paraEsquerda, float graus) {
  rumoGraus = 0.0;
  instanteAnteriorUs = micros();
  unsigned long inicioMs = millis();

  rotacionar(paraEsquerda);
  while (fabs(rumoGraus) < (graus - ANTECIPACAO_GRAUS) &&
         (millis() - inicioMs) < LIMITE_TEMPO_GIRO_MS) {
    integrarGiro();
  }
  pararRobo();
  delay(120);                                  // deixa o robô assentar
}

void reagirAoObstaculo(bool foiQueda) {
  pararRobo();
  delay(120);

  recuar();                                    // afasta do obstáculo
  delay(foiQueda ? TEMPO_RE_MS * 2 : TEMPO_RE_MS);
  pararRobo();
  delay(100);

  // Está preso? Várias batidas em sequência indicam um canto.
  unsigned long agora = millis();
  if (agora - ultimaReacaoMs < JANELA_PRESO_MS) batidasSeguidas++;
  else                                          batidasSeguidas = 1;

  bool  paraEsquerda;
  float graus;

  if (batidasSeguidas >= BLOQUEIOS_PARA_RETORNO) {
    paraEsquerda    = (random(2) == 0);
    graus           = 180.0;                   // meia-volta
    batidasSeguidas = 0;
  } else {
    float livreEsq = ecoMediano(1);
    float livreDir = ecoMediano(2);
    if (livreEsq < 0) livreEsq = DISTANCIA_LONGE_CM;
    if (livreDir < 0) livreDir = DISTANCIA_LONGE_CM;

    if (fabs(livreEsq - livreDir) < 8.0) paraEsquerda = (random(2) == 0);
    else                                 paraEsquerda = (livreEsq > livreDir);

    graus = random(GIRO_MINIMO_GRAUS, GIRO_MAXIMO_GRAUS + 1);
  }

  if (MODO_DEPURACAO) {
    Serial.print(foiQueda ? "QUEDA" : "OBSTACULO");
    Serial.print(" -> gira ");
    Serial.print(paraEsquerda ? "esquerda " : "direita ");
    Serial.print(graus);
    Serial.println(" graus");
  }

  girarPorGraus(paraEsquerda, graus);
  ultimaReacaoMs = millis();
}

// =====================================================================
//  SETUP E LOOP
// =====================================================================
void setup() {
  if (MODO_DEPURACAO) Serial.begin(115200);

  for (uint8_t s = 0; s < 3; s++) {
    pinMode(PINO_DISPARO[s], OUTPUT);
    pinMode(PINO_ECO[s], INPUT);
  }
  if (SENSOR_QUEDA_ATIVO) pinMode(PINO_QUEDA, INPUT);
  if (SUCCAO_ATIVA) {
    pinMode(PINO_SUCCAO, OUTPUT);
    digitalWrite(PINO_SUCCAO, LOW);
  }

  mapearLados();
  pararRobo();

  Wire.begin();
  giroscopio.initialize();
  if (!giroscopio.testConnection()) {          // sem giroscópio, não anda
    pinMode(LED_BUILTIN, OUTPUT);
    while (true) {                             // LED piscando = erro no MPU-6050
      digitalWrite(LED_BUILTIN, HIGH); delay(200);
      digitalWrite(LED_BUILTIN, LOW);  delay(200);
    }
  }

  delay(2500);          // tempo para colocar o robô no chão, parado, NÃO ESQUECER
  calibrarGiro();       // o robô precisa estar imóvel aqui
  randomSeed(analogRead(A15) ^ micros());
  instanteAnteriorUs = micros();

  if (SUCCAO_ATIVA) digitalWrite(PINO_SUCCAO, HIGH);
}

void loop() {
  if (semChaoAFrente()) {
    reagirAoObstaculo(true);
    return;
  }

  float distanciaFrente = ecoMediano(0);
  if (distanciaFrente > 0 && distanciaFrente < LIMITE_OBSTACULO_CM) {
    reagirAoObstaculo(false);
  } else {
    avancar();
  }
}
