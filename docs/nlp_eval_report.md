# NLP Evaluation Report — JARVIS Building Twin

**Date / Time (UTC):** `2026-09-12T06:31:52.787447+00:00`  
**Evaluation Engine:** `deterministic_pattern_parser` (`offline` mode)  
**Test Corpus Size:** `45` labeled cases  
**Runtime Duration:** `0.0s`  

---

## Executive Summary

| Metric | Result | Target | Status |
|---|---|---|---|
| **Out-of-Scope Rejection Rate** | **100.0%** (8/8) | **100.0%** | PASS |
| **Intent Accuracy** | **100.0%** | ≥ 90.0% | PASS |
| **Room Assignment Accuracy** | **100.0%** | ≥ 90.0% | PASS |
| **Overall Accuracy (Exact Match)** | **100.0%** | ≥ 90.0% | PASS |

## Category Breakdown

| Category | Cases | Action Accuracy | Room Accuracy | Full Match |
|---|---|---|---|---|
| `thermal_hot` | 6 | 100.0% | 100.0% | 100.0% |
| `thermal_cold` | 6 | 100.0% | 100.0% | 100.0% |
| `airflow_stuffy` | 4 | 100.0% | 100.0% | 100.0% |
| `airflow_drafty` | 3 | 100.0% | 100.0% | 100.0% |
| `explicit_setpoint` | 3 | 100.0% | 100.0% | 100.0% |
| `room_synonym` | 6 | 100.0% | 100.0% | 100.0% |
| `ambiguous_no_room` | 3 | 100.0% | 100.0% | 100.0% |
| `sarcasm_subtle` | 3 | 100.0% | 100.0% | 100.0% |
| `multilingual` | 3 | 100.0% | 100.0% | 100.0% |
| `out_of_scope` | 8 | 100.0% | 100.0% | 100.0% |

## Failures & Discrepancies

> **Zero failures detected! All 45 test cases parsed with 100% precision.**

## Complete Test Case Results

| ID | Category | Complaint | Expected Action | Expected Room | Predicted Action | Predicted Room | Status |
|---|---|---|---|---|---|---|---|
| TC01 | thermal_hot | Room A is boiling hot right now, we can ... | decrease_temp | A | decrease_temp | A | PASS |
| TC02 | thermal_hot | It feels a bit warm in the engineering r... | decrease_temp | B | decrease_temp | B | PASS |
| TC03 | thermal_hot | Server room C is heating up rapidly, coo... | decrease_temp | C | decrease_temp | C | PASS |
| TC04 | thermal_hot | The reception area D is slightly warmer ... | decrease_temp | D | decrease_temp | D | PASS |
| TC05 | thermal_hot | We are sweating in the boardroom, please... | decrease_temp | A | decrease_temp | A | PASS |
| TC06 | thermal_hot | Room B is scorching, please blast the AC... | decrease_temp | B | decrease_temp | B | PASS |
| TC07 | thermal_cold | Room A is freezing cold, our teeth are c... | increase_temp | A | increase_temp | A | PASS |
| TC08 | thermal_cold | Engineering pit B is a little chilly thi... | increase_temp | B | increase_temp | B | PASS |
| TC09 | thermal_cold | Room C temperature is way too low, turn ... | increase_temp | C | increase_temp | C | PASS |
| TC10 | thermal_cold | The front desk D feels like an icebox to... | increase_temp | D | increase_temp | D | PASS |
| TC11 | thermal_cold | Can we bump up the heat slightly in room... | increase_temp | A | increase_temp | A | PASS |
| TC12 | thermal_cold | Devs in room B are shivering with winter... | increase_temp | B | increase_temp | B | PASS |
| TC13 | airflow_stuffy | The air in Room A is so stuffy and heavy... | increase_airflow | A | increase_airflow | A | PASS |
| TC14 | airflow_stuffy | Room B feels suffocating and stale, we n... | increase_airflow | B | increase_airflow | B | PASS |
| TC15 | airflow_stuffy | It's slightly stuffy in the IT server cl... | increase_airflow | C | increase_airflow | C | PASS |
| TC16 | airflow_stuffy | Reception D has terrible air quality and... | increase_airflow | D | increase_airflow | D | PASS |
| TC17 | airflow_drafty | There is an extreme draft blowing right ... | decrease_airflow | A | decrease_airflow | A | PASS |
| TC18 | airflow_drafty | Vents in room B are blowing papers off t... | decrease_airflow | B | decrease_airflow | B | PASS |
| TC19 | airflow_drafty | Way too much wind coming from the AC ven... | decrease_airflow | D | decrease_airflow | D | PASS |
| TC20 | explicit_setpoint | Please set room A to exactly 23°C for ou... | set_setpoint | A | set_setpoint | A | PASS |
| TC21 | explicit_setpoint | Set temperature in room B to 21 degrees ... | set_setpoint | B | set_setpoint | B | PASS |
| TC22 | explicit_setpoint | Thermostat for server room C should be s... | set_setpoint | C | set_setpoint | C | PASS |
| TC23 | room_synonym | The big meeting room is sweltering hot.... | decrease_temp | A | decrease_temp | A | PASS |
| TC24 | room_synonym | Where the devs sit is uncomfortably warm... | decrease_temp | B | decrease_temp | B | PASS |
| TC25 | room_synonym | The developer pit is completely freezing... | increase_temp | B | increase_temp | B | PASS |
| TC26 | room_synonym | Data center and server racks are overhea... | decrease_temp | C | decrease_temp | C | PASS |
| TC27 | room_synonym | The front entrance lobby has stale, stuf... | increase_airflow | D | increase_airflow | D | PASS |
| TC28 | room_synonym | Visitors in the waiting area are complai... | increase_temp | D | increase_temp | D | PASS |
| TC29 | ambiguous_no_room | It is way too cold in here, turn up the ... | increase_temp | None | increase_temp | None | PASS |
| TC30 | ambiguous_no_room | Air quality is awful in this building, c... | increase_airflow | None | increase_airflow | None | PASS |
| TC31 | ambiguous_no_room | It feels really hot and humid everywhere... | decrease_temp | None | decrease_temp | None | PASS |
| TC32 | sarcasm_subtle | Loving the arctic expedition we are havi... | increase_temp | A | increase_temp | A | PASS |
| TC33 | sarcasm_subtle | Did someone turn Room B into a sauna? Sw... | decrease_temp | B | decrease_temp | B | PASS |
| TC34 | sarcasm_subtle | Great hurricane simulation in the lobby,... | decrease_airflow | D | decrease_airflow | D | PASS |
| TC35 | multilingual | Hace demasiado calor en la sala de confe... | decrease_temp | A | decrease_temp | A | PASS |
| TC36 | multilingual | Il fait très froid dans le bureau des dé... | increase_temp | B | increase_temp | B | PASS |
| TC37 | multilingual | Room D mein bohot garmi hai, AC chalao p... | decrease_temp | D | decrease_temp | D | PASS |
| TC38 | out_of_scope | My office ergonomic chair is broken and ... | none | None | none | None | PASS |
| TC39 | out_of_scope | It's way too noisy in Room B, people are... | none | None | none | None | PASS |
| TC40 | out_of_scope | There is terrible sun glare on my monito... | none | None | none | None | PASS |
| TC41 | out_of_scope | The coffee machine in the kitchen is com... | none | None | none | None | PASS |
| TC42 | out_of_scope | The Wi-Fi in room D keeps disconnecting ... | none | None | none | None | PASS |
| TC43 | out_of_scope | Someone spilled soda on the carpet near ... | none | None | none | None | PASS |
| TC44 | out_of_scope | My keyboard spacebar is stuck and mouse ... | none | None | none | None | PASS |
| TC45 | out_of_scope | The overhead fluorescent light fixture i... | none | None | none | None | PASS |
