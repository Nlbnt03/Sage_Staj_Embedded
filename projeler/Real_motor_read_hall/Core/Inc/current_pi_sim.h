#ifndef CURRENT_PI_SIM_H
#define CURRENT_PI_SIM_H

#include <stdint.h>

/* Bu modul mekanik hizi veya encoder darbesini simule etmez. Gercek RPM'i
   giris olarak alir; yalnizca PI duty degerini ve sanal faz akimini hesaplar. */
#define CURRENT_PI_STEP_MS          10U
#define CURRENT_PI_MAX_CURRENT_A    20.0f
#define CURRENT_PI_DEFAULT_INPUTS   {3.0f, 2.0f, 20.0f, 24.0f, 0.60f, 0.030f, 0.050f, 1U}

typedef enum
{
  PHASE_NONE = 0,
  PHASE_A,
  PHASE_B,
  PHASE_C
} MotorPhase;

typedef struct
{
  uint8_t sector;
  MotorPhase high_phase;
  MotorPhase low_phase;
  MotorPhase floating_phase;
  uint8_t valid;
} CommutationState;

typedef struct
{
  float target_current_a;
  float kp_percent_per_a;
  float ki_percent_per_a_s;
  float bus_voltage_v;
  float phase_resistance_ohm;
  float phase_inductance_h;
  float bemf_constant_v_per_rad_s;
  uint32_t enabled;
} CurrentPiInputs;

typedef struct
{
  float real_rpm;
  float target_current_a;
  float fake_current_a;
  float error_a;
  float duty_percent;
  float integral_percent;
  float back_emf_v;
  float applied_voltage_v;
  uint8_t hall_state;
  CommutationState commutation;
  uint32_t elapsed_ms;
  CurrentPiInputs applied_inputs;
} CurrentPiState;

void CurrentPi_Init(CurrentPiState *state);
CommutationState CurrentPi_DecodeHall(uint8_t hall_state);
void CurrentPi_Step(CurrentPiState *state,
                    const CurrentPiInputs *inputs,
                    float real_rpm,
                    uint8_t hall_state);

#endif
