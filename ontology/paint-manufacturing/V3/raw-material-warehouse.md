# Concept: Raw Material Warehouse

## Canonical
raw material warehouse

## Type
entity

## Aliases
- rm warehouse
- inbound material warehouse

## Definition
A raw material warehouse is the plant storage area dedicated to inbound ingredients and other manufacturing inputs before line consumption.

## Related
- type: stores
  concept: raw material

## Parents
- warehouse

## Attributes
- storage zones
- lot traceability
- handling conditions

## ExampleQueries
- where are raw materials stored
- what is kept in the raw material warehouse

## Tags
- warehouse
- raw materials
- inbound

## Synonyms
- material store

## Notes
This warehouse supports line feeding and inbound inventory control.

## Constraints
- must segregate incompatible material classes
- must preserve raw material traceability

## QueryHints
- boost: rm warehouse
- boost: inbound material store

## AnswerRequirements
- definition
- mechanism
- comparison
