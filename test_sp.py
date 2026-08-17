import sys
from backend.digital_twin import BuildingTwin

twin = BuildingTwin(outside_temperature_c=34.0)

print(f"Initial T: {twin.get_state()['rooms']['A']['temperature_c']}")
twin.set_setpoint('A', 20.0)

for i in range(10):
    twin.step()
    state = twin.get_state()
    t = state['rooms']['A']['temperature_c']
    q_hvac = state['rooms']['A']['hvac_power_kw']
    print(f"Step {i+1}: T={t:.2f} Q_hvac={q_hvac:.2f}")

