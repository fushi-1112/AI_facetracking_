
#include <Servo.h>

Servo trackingServo;

const int SERVO_PIN = 9;

const int MIN_ANGLE = 20;
const int MAX_ANGLE = 160;

float servoAngle = 90;

bool servoAttached = false;

unsigned long lastSignalTime = 0;

const unsigned long SIGNAL_TIMEOUT = 500;


void setup() {

  Serial.begin(9600);

  lastSignalTime = millis();
}


void loop() {

  // ==================================================
  // RECEIVE DATA
  // ==================================================

  if (Serial.available() > 0) {

    String data = Serial.readStringUntil('\n');

    data.trim();


    // ==================================================
    // STOP
    // ==================================================

    if (data == "STOP") {

      if (servoAttached) {

        trackingServo.detach();

        servoAttached = false;
      }

      return;
    }


    // ==================================================
    // ANGLE
    // ==================================================

    if (data.startsWith("ANGLE:")) {

      String value = data.substring(6);

      float angle = value.toFloat();


      angle = constrain(
        angle,
        MIN_ANGLE,
        MAX_ANGLE
      );


      servoAngle = angle;


      // Attach Servo ถ้ายังไม่ได้ attach

      if (!servoAttached) {

        trackingServo.attach(SERVO_PIN);

        servoAttached = true;
      }


      trackingServo.write(
        (int)servoAngle
      );


      lastSignalTime = millis();
    }
  }


  // ==================================================
  // PYTHON หาย / CRASH
  // ==================================================

  if (
    servoAttached &&
    millis() - lastSignalTime > SIGNAL_TIMEOUT
  ) {

    trackingServo.detach();

    servoAttached = false;
  }
}

