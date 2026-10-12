# Evaluation results

- Run date: 2026-10-12 03:31 UTC
- Model: gpt-5-mini
- Commit: 8e20659
- Experiment: octi-eval-1d229222

| id | Question | Expected | Actual | Status | Values | Tables | Retries | Trace |
|---|---|---|---|---|---|---|---|---|
| q01 | What was ACME's net revenue in 2023? | answered | answered | ✓ | ✓ | ✓ | 0 | [trace](https://aws.smith.langchain.com/o/50bc837b-4a85-42c3-b2bf-b6c08a10d73a/projects/p/2f3a0553-74b3-4e4b-a657-fa20dbc49d37/r/01a12e28-e18d-7b20-855d-3b61e8f6c77a?poll=true) |
| q02 | Using the monthly sales table, what were ACME's total net sales in 2022, in USD millions? | answered | answered | ✓ | ✓ | ✓ | 0 | [trace](https://aws.smith.langchain.com/o/50bc837b-4a85-42c3-b2bf-b6c08a10d73a/projects/p/2f3a0553-74b3-4e4b-a657-fa20dbc49d37/r/01a12e28-6437-7a92-a0da-fe1060a9b204?poll=true) |
| q03 | ¿Cuál fue la tasa de desempleo de Cuyo en 2023? | answered | answered | ✓ | ✓ | ✓ | 0 | [trace](https://aws.smith.langchain.com/o/50bc837b-4a85-42c3-b2bf-b6c08a10d73a/projects/p/2f3a0553-74b3-4e4b-a657-fa20dbc49d37/r/01a12e27-fede-7110-9fa6-725c4b1becae?poll=true) |
| q04 | What share of ACME's net revenue did R&D expenses represent in 2023? | answered | answered | ✓ | ✓ | ✓ | 0 | [trace](https://aws.smith.langchain.com/o/50bc837b-4a85-42c3-b2bf-b6c08a10d73a/projects/p/2f3a0553-74b3-4e4b-a657-fa20dbc49d37/r/01a12e27-99fe-7e40-b57f-246e213b4f9c?poll=true) |
| q05 | What were ACME's net sales per inhabitant in Patagonia in 2023, in USD? | answered | answered | ✓ | ✓ | ✓ | 0 | [trace](https://aws.smith.langchain.com/o/50bc837b-4a85-42c3-b2bf-b6c08a10d73a/projects/p/2f3a0553-74b3-4e4b-a657-fa20dbc49d37/r/01a12e27-2088-7551-be40-139d17c75090?poll=true) |
| q06 | What was ACME's carbon footprint in 2023? | cannot_answer | cannot_answer | ✓ | – | ✓ | 0 | [trace](https://aws.smith.langchain.com/o/50bc837b-4a85-42c3-b2bf-b6c08a10d73a/projects/p/2f3a0553-74b3-4e4b-a657-fa20dbc49d37/r/01a12e29-c0ae-70a3-b8b6-2367f1c5d288?poll=true) |
| q07 | What was ACME's net income in 2019? | cannot_answer | cannot_answer | ✓ | – | ✓ | 0 | [trace](https://aws.smith.langchain.com/o/50bc837b-4a85-42c3-b2bf-b6c08a10d73a/projects/p/2f3a0553-74b3-4e4b-a657-fa20dbc49d37/r/01a12e29-8106-7f62-a100-99b84c685532?poll=true) |
| q08 | What were ACME's R&D expenses in 2023, and how much did it spend on advertising in 2023? | partial | partial | ✓ | ✓ | ✓ | 0 | [trace](https://aws.smith.langchain.com/o/50bc837b-4a85-42c3-b2bf-b6c08a10d73a/projects/p/2f3a0553-74b3-4e4b-a657-fa20dbc49d37/r/01a12e26-a907-71b3-9d44-aeaacf47f3df?poll=true) |
| q09 | What was ACME's market share in Patagonia in 2023, and how does it compare with ACME's national market share? | partial | cannot_answer | ✗ | ✗ | ✓ | 2 | [trace](https://aws.smith.langchain.com/o/50bc837b-4a85-42c3-b2bf-b6c08a10d73a/projects/p/2f3a0553-74b3-4e4b-a657-fa20dbc49d37/r/01a12e25-c117-76c0-8c82-3ecc7ebeb565?poll=true) |
| q10 | What was ACME's revenue in 2022? | cannot_answer | cannot_answer | ✓ | – | ✓ | 0 | [trace](https://aws.smith.langchain.com/o/50bc837b-4a85-42c3-b2bf-b6c08a10d73a/projects/p/2f3a0553-74b3-4e4b-a657-fa20dbc49d37/r/01a12e29-381d-73e0-a795-30624dbee4ca?poll=true) |

## Totals

- status_correct: 9/10
- values_correct: 6/7 (3 not applicable)
- tables_correct: 10/10
