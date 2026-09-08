#include "motor_sim.h"
#include <math.h>

#define MOTOR_TIME_CONSTANT_S  0.30f
#define DERIVATIVE_FILTER_S    0.05f

static float Clamp(float value, float low, float high)
{
  if (!isfinite(value))
  {
    return low;
  }
  return value < low ? low : (value > high ? high : value);
}

void MotorSim_Init(MotorSimState *state)
{
  *state = (MotorSimState){0};
}

void MotorSim_Step(MotorSimState *state, const MotorSimInputs *inputs)
{
  const float dt = (float)MOTOR_SIM_STEP_MS * 0.001f;
  const float kp = Clamp(inputs->kp, 0.0f, 10.0f);
  const float ki = Clamp(inputs->ki, 0.0f, 10.0f);
  const float kd = Clamp(inputs->kd, 0.0f, 10.0f);
  const float load = Clamp(inputs->load_rpm, 0.0f, MOTOR_SIM_MAX_RPM);
  float error;
  float equilibrium_rpm;
  float counts;
  uint32_t delta_count;

  state->target_rpm = Clamp(inputs->target_rpm, 0.0f, MOTOR_SIM_MAX_RPM);
  state->applied_inputs = (MotorSimInputs){
    state->target_rpm, kp, ki, kd, load, inputs->enabled != 0U
  };
  error = state->target_rpm - state->measured_rpm;

  /* Turev olcumden alinir: hedef hiz degisimi turev darbesi uretmez. */
  state->derivative_rpm_s += dt / (DERIVATIVE_FILTER_S + dt) *
      ((state->measured_rpm - state->previous_rpm) / dt - state->derivative_rpm_s);
  state->previous_rpm = state->measured_rpm;

  if (inputs->enabled == 0U || state->target_rpm == 0.0f)
  {
    state->integral_percent = 0.0f;
    state->derivative_rpm_s = 0.0f;
    state->duty_percent = 0.0f;
  }
  else
  {
    float increment = ki * error * dt;
    float candidate;
    float output;
    if (ki == 0.0f)
    {
      state->integral_percent = 0.0f;
    }
    candidate = Clamp(state->integral_percent + increment, 0.0f, 100.0f);
    output = kp * error + state->integral_percent - kd * state->derivative_rpm_s;

    /* Anti-windup: mevcut cikis doyumdaysa o yonde integrasyonu durdur.
       Aday cikisla kontrol etmek, sinira ulasmadan I'yi dondurabilir. */
    if ((output <= 100.0f || increment < 0.0f) &&
        (output >= 0.0f || increment > 0.0f))
    {
      state->integral_percent = candidate;
    }
    state->duty_percent = Clamp(kp * error + state->integral_percent -
                               kd * state->derivative_rpm_s, 0.0f, 100.0f);
  }

  /* Birinci dereceden, tek yonlu motor: tau * dRPM/dt = RPM_eq - RPM.
     Yuk tork modeli degil, esdeger denge hizi kaybidir. */
  equilibrium_rpm = Clamp(MOTOR_SIM_MAX_RPM * state->duty_percent / 100.0f -
                          load, 0.0f, MOTOR_SIM_MAX_RPM);
  state->model_rpm += dt / (MOTOR_TIME_CONSTANT_S + dt) *
                      (equilibrium_rpm - state->model_rpm);

  /* Kesirli darbeleri saklayarak dusuk hizda sayim kaybini onle. */
  counts = state->fractional_count + state->model_rpm * dt *
           (float)MOTOR_SIM_COUNTS_PER_REV / 60.0f;
  delta_count = (uint32_t)counts;
  state->fractional_count = counts - (float)delta_count;
  state->encoder_count += delta_count;
  state->measured_rpm = (float)delta_count * 60.0f /
                        ((float)MOTOR_SIM_COUNTS_PER_REV * dt);
  state->error_rpm = state->target_rpm - state->measured_rpm;
  state->elapsed_ms += MOTOR_SIM_STEP_MS;
}
