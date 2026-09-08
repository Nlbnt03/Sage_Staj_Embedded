#ifndef MOTOR_SIM_H
#define MOTOR_SIM_H

#include <stdint.h>

/* Yalnizca yazilim modeli: bu modul GPIO/PWM/HAL kullanmaz. */
#define MOTOR_SIM_STEP_MS             10U
#define MOTOR_SIM_COUNTS_PER_REV      (4096U * 4U)
#define MOTOR_SIM_MAX_RPM             3000.0f
#define MOTOR_SIM_DEFAULT_INPUTS      {1500.0f, 0.03f, 0.08f, 0.0005f, 0.0f, 1U}

typedef struct
{
  float target_rpm;
  float kp;                  /* % / RPM */
  float ki;                  /* % / (RPM * saniye) */
  float kd;                  /* % * saniye / RPM */
  float load_rpm;            /* Yuk: tam gazdaki denge hizindan dusulen RPM */
  uint32_t enabled;          /* 0: cikis sifir, motor serbestce yavaslar */
} MotorSimInputs;

typedef struct
{
  float target_rpm;
  float measured_rpm;        /* Sanal enkoderin 10 ms sayim farkindan */
  float model_rpm;
  float error_rpm;
  float duty_percent;        /* Sadece sayisal deger; pine uygulanmaz */
  float integral_percent;
  float derivative_rpm_s;
  float previous_rpm;
  float fractional_count;
  uint32_t encoder_count;    /* 32-bit sayac, tasma moduler */
  uint32_t elapsed_ms;
  /* Son adimda gercekten kullanilan, sinirlanmis ayarlar (UART/debug). */
  MotorSimInputs applied_inputs;
} MotorSimState;

void MotorSim_Init(MotorSimState *state);
/* Her cagri tam MOTOR_SIM_STEP_MS kadar sanal zamani ilerletir. */
void MotorSim_Step(MotorSimState *state, const MotorSimInputs *inputs);

#endif
