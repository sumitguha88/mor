# Concept: Plant

## Canonical
plant

## Type
entity

## Aliases
- manufacturing plant
- factory
- production site

## Definition
A plant is the physical operating site where paint products are manufactured, raw materials are received, inventory is stored, and finished goods are dispatched into the distribution network.

## Related
- type: has_production_line
  concept: production line
- type: has_warehouse
  concept: warehouse
- type: has_warehouse
  concept: raw material warehouse
- type: has_warehouse
  concept: finished goods warehouse

## Attributes
- location
- site code
- production capacity
- warehouse footprint

## ExampleQueries
- which plant has which production lines
- what warehouses belong to a plant

## Tags
- manufacturing
- facility
- operations

## Synonyms
- manufacturing facility
- production facility

## Notes
Plant is the main operational node that connects production and internal storage.

## Constraints
- must have at least one production line
- must have warehouse capacity for inbound and outbound inventory

## QueryHints
- boost: factory
- boost: manufacturing site

## AnswerRequirements
- definition
- mechanism
- comparison
