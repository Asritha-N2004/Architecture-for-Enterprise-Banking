# Evaluation scaffold

`python evaluation/run_controls.py` executes the implemented control suite and writes measured elapsed time and JUnit counts under results/. These are software test observations, not workflow accuracy or comparative research findings.

E1–E6 and ablations remain unimplemented. They require isolated executables, a fixed synthetic workload, scenario labels, repeated runs, latency distributions, authorization confusion matrices, independent completion scoring, provider/model versions, environment metadata and confidence intervals. Weakening production controls to simulate a baseline is not supported. Build unsafe baselines only inside a separate isolated evaluation harness with synthetic data. No research result should be reported until that experiment actually runs.
