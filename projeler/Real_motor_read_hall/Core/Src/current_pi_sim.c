#include "current_pi_sim.h"

#include <math.h>

#define TWO_PI_OVER_60  0.1047197551f

static float Clamp(float value, float low, float high)
{
  if (!isfinite(value))
  {
    return low;
  }
  return value < low ? low : (value > high ? high : value);
}

CommutationState CurrentPi_DecodeHall(uint8_t hall_state)
{
  static const CommutationState table[8] =
  {
    {0U, PHASE_NONE, PHASE_NONE, PHASE_NONE, 0U},
    {1U, PHASE_A,    PHASE_B,    PHASE_C,    1U},
    {5U, PHASE_C,    PHASE_A,    PHASE_B,    1U},
    {6U, PHASE_C,    PHASE_B,    PHASE_A,    1U},
    {3U, PHASE_B,    PHASE_C,    PHASE_A,    1U},
    {2U, PHASE_A,    PHASE_C,    PHASE_B,    1U},
    {4U, PHASE_B,    PHASE_A,    PHASE_C,    1U},
    {0U, PHASE_NONE, PHASE_NONE, PHASE_NONE, 0U}
  };

  return table[hall_state & 0x07U];
}

void CurrentPi_Init(CurrentPiState *state)
{
  *state = (CurrentPiState){0};
}

void CurrentPi_Step(CurrentPiState *state,
                    const CurrentPiInputs *inputs,
                    float real_rpm,
                    uint8_t hall_state)
{
  const float dt = (float)CURRENT_PI_STEP_MS * 0.001f;
  const float kp = Clamp(inputs->kp_percent_per_a, 0.0f, 100.0f);
  const float ki = Clamp(inputs->ki_percent_per_a_s, 0.0f, 1000.0f);
  const float bus_voltage = Clamp(inputs->bus_voltage_v, 0.1f, 1000.0f);
  const float resistance = Clamp(inputs->phase_resistance_ohm, 0.001f, 1000.0f);
  const float inductance = Clamp(inputs->phase_inductance_h, 0.000001f, 100.0f);
  const float bemf_constant = Clamp(inputs->bemf_constant_v_per_rad_s, 0.0f, 100.0f);
  float rpm;
  float error;
  float p_term;
  float unsaturated;
  float integral_increment;
  float voltage_difference;
  float dt_over_l;

  if (!isfinite(real_rpm))
  {
    real_rpm = 0.0f;
  }
  rpm = real_rpm < 0.0f ? -real_rpm : real_rpm;

  state->hall_state = hall_state & 0x07U;
  state->commutation = CurrentPi_DecodeHall(state->hall_state);
  state->real_rpm = real_rpm;
  state->target_current_a = Clamp(inputs->target_current_a,
                                  0.0f, CURRENT_PI_MAX_CURRENT_A);
  state->applied_inputs = (CurrentPiInputs){
    state->target_current_a, kp, ki, bus_voltage, resistance, inductance,
    bemf_constant, inputs->enabled != 0U
  };

  error = state->target_current_a - state->fake_current_a;
  p_term = kp * error;
  integral_increment = ki * error * dt;
  unsaturated = p_term + state->integral_percent;

  if (inputs->enabled == 0U || state->commutation.valid == 0U)
  {
    state->integral_percent = 0.0f;
    state->duty_percent = 0.0f;
  }
  else
  {
    if ((unsaturated < 100.0f || integral_increment < 0.0f) &&
        (unsaturated > 0.0f || integral_increment > 0.0f))
    {
      state->integral_percent = Clamp(state->integral_percent + integral_increment,
                                      0.0f, 100.0f);
    }
    state->duty_percent = Clamp(p_term + state->integral_percent, 0.0f, 100.0f);
  }

  state->back_emf_v = bemf_constant * rpm * TWO_PI_OVER_60;
  state->applied_voltage_v = bus_voltage * state->duty_percent / 100.0f;
  voltage_difference = state->applied_voltage_v - state->back_emf_v;
  dt_over_l = dt / inductance;
  state->fake_current_a = Clamp(
      (state->fake_current_a + dt_over_l * voltage_difference) /
      (1.0f + dt_over_l * resistance),
      0.0f, CURRENT_PI_MAX_CURRENT_A);

  state->error_a = state->target_current_a - state->fake_current_a;
  state->elapsed_ms += CURRENT_PI_STEP_MS;
}
