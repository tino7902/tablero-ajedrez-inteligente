// Firmware del Arduino Nano que barre la matriz de 64 sensores Hall (v3 de la detección de
// casillas). No hace nada por su cuenta: la Raspberry Pi (o una persona en el monitor serie)
// manda un comando por línea y el Nano contesta una línea. El antirrebote, la calibración y
// el mapeo celda → casilla los hace la Pi; acá solo están las primitivas del barrido.
//
// Protocolo completo en software-docs/firmware-nano.md; cableado en
// hardware-docs/matriz-hall-nano.md. Serie a 115200 baudios.
//
//   ?        → LISTO matriz-nano 1
//   L [µs]   → M b0 b1 .. b7   barre F0..F7 (bk = fila Fk en hex, bit c = columna Ck, 1 = imán)
//   F k      → OK Fk           deja encendida fija la fila k (para medir con el multímetro)
//   C        → C bb            lee las columnas sin tocar las filas
//   X        → OK X            apaga todas las filas
//   A        → A v0 .. v7      lectura analógica cruda de cada columna ('-' si no es analógica)
//   V [µs]   → grilla de '#' y '.' cada 500 ms, hasta la próxima línea
//   otro     → ERR comando | ERR argumento | ERR largo

// Plan B (columnas leídas como analógicas, ver hardware-docs/matriz-hall-nano.md): compilar
// con -DPLAN_B=1 o cambiar el 0 de abajo. El umbral se elige mirando lo que da el comando A.
#ifndef PLAN_B
#define PLAN_B 0
#endif
#ifndef UMBRAL_PLAN_B
#define UMBRAL_PLAN_B 512  // ~2,5 V; por debajo, imán
#endif

#define VERSION_PROTOCOLO "1"

// Fila Fk y columna Ck conservan el número del cable que iba a Yk del 74HC138 y a Dk del
// 74HC165, para que CASILLA_DE_CELDA_HALL de config.py siga valiendo.
const uint8_t FILAS[8] = {2, 3, 4, 5, 6, 7, 8, 9};
#if PLAN_B
const uint8_t COLUMNAS[8] = {A5, A6, A7, A0, A1, A2, A3, A4};
const bool ES_ANALOGICA[8] = {true, true, true, true, true, true, true, true};
#else
const uint8_t COLUMNAS[8] = {10, 11, 12, A0, A1, A2, A3, A4};
const bool ES_ANALOGICA[8] = {false, false, false, true, true, true, true, true};
#endif

const unsigned long ESPERA_POR_DEFECTO_US = 1000;  // igual que HALL_ESPERA_ENCENDIDO
const unsigned long ESPERA_MAXIMA_US = 50000;
const unsigned long PERIODO_VISTA_MS = 500;
const uint8_t LARGO_MAXIMO_LINEA = 15;

enum Argumento { SIN_ARGUMENTO, ARGUMENTO_VALIDO, ARGUMENTO_INVALIDO };

char linea[LARGO_MAXIMO_LINEA + 1];
uint8_t largo = 0;
bool desbordada = false;  // la línea en curso pasó de LARGO_MAXIMO_LINEA

bool vistaActiva = false;
unsigned long esperaVistaUs = ESPERA_POR_DEFECTO_US;
unsigned long ultimaVista = 0;

// -- Matriz -------------------------------------------------------------------------------

void apagarFilas() {
  for (uint8_t f = 0; f < 8; f++) digitalWrite(FILAS[f], LOW);
}

void encenderFila(uint8_t fila) {
  apagarFilas();
  digitalWrite(FILAS[fila], HIGH);  // el NPN conduce y conecta a GND el bus de la fila
}

// delayMicroseconds solo es preciso hasta ~16 ms: los milisegundos enteros van con delay.
void esperarUs(unsigned long us) {
  if (us >= 1000) delay(us / 1000);
  delayMicroseconds((unsigned int)(us % 1000));
}

// El ADC muestrea con un capacitor que se carga a través de la pull-up (~35 kΩ, mucha
// impedancia para el ADC): la primera lectura después de cambiar de canal arrastra algo
// del canal anterior, así que se descarta.
int leerAnalogico(uint8_t pin) {
  analogRead(pin);
  return analogRead(pin);
}

// Bit c en 1 = la columna Ck está en LOW = imán sobre esa casilla de la fila encendida.
uint8_t leerColumnas() {
  uint8_t columnas = 0;
  for (uint8_t c = 0; c < 8; c++) {
#if PLAN_B
    bool iman = leerAnalogico(COLUMNAS[c]) < UMBRAL_PLAN_B;
#else
    bool iman = digitalRead(COLUMNAS[c]) == LOW;
#endif
    if (iman) columnas |= (uint8_t)(1 << c);
  }
  return columnas;
}

// Enciende F0..F7 de a una, espera `esperaUs` a que arranquen sus Hall y lee las columnas.
// Termina con todas las filas apagadas.
void barrer(unsigned long esperaUs, uint8_t filas[8]) {
  for (uint8_t f = 0; f < 8; f++) {
    encenderFila(f);
    esperarUs(esperaUs);
    filas[f] = leerColumnas();
  }
  apagarFilas();
}

// -- Respuestas ---------------------------------------------------------------------------

void imprimirHex(uint8_t valor) {
  if (valor < 0x10) Serial.print('0');
  Serial.print(valor, HEX);
}

void anunciar() {
  Serial.println(F("LISTO matriz-nano " VERSION_PROTOCOLO));
}

void responderError(const __FlashStringHelper* motivo) {
  Serial.print(F("ERR "));
  Serial.println(motivo);
}

void responderMatriz(unsigned long esperaUs) {
  uint8_t filas[8];
  barrer(esperaUs, filas);
  Serial.print('M');
  for (uint8_t f = 0; f < 8; f++) {
    Serial.print(' ');
    imprimirHex(filas[f]);
  }
  Serial.println();
}

void responderColumnas() {
  Serial.print(F("C "));
  imprimirHex(leerColumnas());
  Serial.println();
}

void responderAnalogico() {
  Serial.print('A');
  for (uint8_t c = 0; c < 8; c++) {
    Serial.print(' ');
    if (ES_ANALOGICA[c]) {
      Serial.print(leerAnalogico(COLUMNAS[c]));
    } else {
      Serial.print('-');
    }
  }
  Serial.println();
}

// Una línea por fila (F0..F7) y un carácter por columna (C0..C7): '#' = imán, '.' = vacío.
void imprimirVista() {
  uint8_t filas[8];
  barrer(esperaVistaUs, filas);
  Serial.println(F("   01234567"));
  for (uint8_t f = 0; f < 8; f++) {
    Serial.print('F');
    Serial.print(f);
    Serial.print(' ');
    for (uint8_t c = 0; c < 8; c++) Serial.print((filas[f] & (1 << c)) ? '#' : '.');
    Serial.println();
  }
  Serial.println();
}

// -- Comandos -----------------------------------------------------------------------------

const char* saltarEspacios(const char* p) {
  while (*p == ' ' || *p == '\t') p++;
  return p;
}

bool sinArgumento(const char* texto) {
  return *saltarEspacios(texto) == '\0';
}

// Lo que sigue al comando: nada, o un número de 0 a `maximo` con espacios alrededor.
Argumento leerArgumento(const char* texto, unsigned long maximo, unsigned long& valor) {
  const char* p = saltarEspacios(texto);
  if (*p == '\0') return SIN_ARGUMENTO;
  if (*p < '0' || *p > '9') return ARGUMENTO_INVALIDO;
  valor = 0;
  while (*p >= '0' && *p <= '9') {
    valor = valor * 10 + (unsigned long)(*p - '0');
    if (valor > maximo) return ARGUMENTO_INVALIDO;
    p++;
  }
  return sinArgumento(p) ? ARGUMENTO_VALIDO : ARGUMENTO_INVALIDO;
}

// Espera por fila de L y V: sin número, la de por defecto.
bool leerEspera(const char* texto, unsigned long& espera) {
  switch (leerArgumento(texto, ESPERA_MAXIMA_US, espera)) {
    case SIN_ARGUMENTO:
      espera = ESPERA_POR_DEFECTO_US;
      return true;
    case ARGUMENTO_VALIDO:
      return true;
    default:
      return false;
  }
}

void procesar(const char* texto) {
  const char* p = saltarEspacios(texto);
  if (*p == '\0') return;  // línea con solo espacios
  char comando = (char)toupper((unsigned char)*p);
  const char* resto = p + 1;
  unsigned long valor = 0;

  // Cada caso responde y sale; los `break` son argumentos que sobran, faltan o no valen.
  switch (comando) {
    case '?':
      if (!sinArgumento(resto)) break;
      anunciar();
      return;
    case 'L':
      if (!leerEspera(resto, valor)) break;
      responderMatriz(valor);
      return;
    case 'F':
      if (leerArgumento(resto, 7, valor) != ARGUMENTO_VALIDO) break;
      encenderFila((uint8_t)valor);
      Serial.print(F("OK F"));
      Serial.println(valor);
      return;
    case 'C':
      if (!sinArgumento(resto)) break;
      responderColumnas();
      return;
    case 'X':
      if (!sinArgumento(resto)) break;
      apagarFilas();
      Serial.println(F("OK X"));
      return;
    case 'A':
      if (!sinArgumento(resto)) break;
      responderAnalogico();
      return;
    case 'V':
      if (!leerEspera(resto, valor)) break;
      esperaVistaUs = valor;
      vistaActiva = true;
      ultimaVista = millis() - PERIODO_VISTA_MS;  // la primera grilla sale enseguida
      return;
    default:
      responderError(F("comando"));
      return;
  }
  responderError(F("argumento"));
}

// Junta los caracteres que llegan hasta un fin de línea (\n, \r o \r\n) sin bloquear.
// Cualquier línea nueva corta la vista en vivo antes de procesarse.
void leerSerie() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r' || c == '\n') {
      if (desbordada) {
        vistaActiva = false;
        responderError(F("largo"));
      } else if (largo > 0) {
        linea[largo] = '\0';
        vistaActiva = false;
        procesar(linea);
      }
      largo = 0;
      desbordada = false;
    } else if (largo < LARGO_MAXIMO_LINEA) {
      linea[largo++] = c;
    } else {
      desbordada = true;
    }
  }
}

// -- Arranque y bucle ---------------------------------------------------------------------

void setup() {
  // Las filas, antes que nada. Hasta acá cada pin es una entrada y la 10 kΩ entre base y GND
  // tiene apagado su NPN; se pone el LOW antes de hacerlo salida para que no haya un pulso.
  for (uint8_t f = 0; f < 8; f++) {
    digitalWrite(FILAS[f], LOW);
    pinMode(FILAS[f], OUTPUT);
  }
  for (uint8_t c = 0; c < 8; c++) {
    // A6 y A7 son solo analógicas: no tienen pull-up interna (en el plan B llevan una de
    // 10 kΩ externa) y pinMode no las conoce.
    if (COLUMNAS[c] == A6 || COLUMNAS[c] == A7) continue;
    pinMode(COLUMNAS[c], INPUT_PULLUP);
  }
  Serial.begin(115200);
  // Al abrir el puerto el Nano se resetea y por el USB suele entrar algo de basura; el salto de
  // línea la deja sola en su línea y el LISTO llega limpio.
  Serial.println();
  anunciar();
}

void loop() {
  leerSerie();
  if (vistaActiva && millis() - ultimaVista >= PERIODO_VISTA_MS) {
    ultimaVista = millis();
    imprimirVista();
  }
}
