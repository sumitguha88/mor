# Marketing Sample Ontology

This sample ontology models a marketing organization with concepts for campaign planning, audience segmentation, channels, creative assets, measurement, and lead handling.

## Validate the sample ontology

```bash
mor validate --ontology-root ontology --area marketing --version V1
```

## Try resolution and expansion

```bash
mor resolve "paid search" --ontology-root ontology --area marketing --version V1
mor expand "how do we measure campaign conversion performance" --ontology-root ontology --area marketing --version V1
mor scaffold --intent architecture_explanation --query "explain audience segmentation and campaign attribution" --ontology-root ontology --area marketing --version V1
```

## Run the sample benchmark

```bash
mor benchmark \
  --cases-path examples/marketing/benchmark_cases.json \
  --ontology-root ontology \
  --area marketing \
  --version V1
```
