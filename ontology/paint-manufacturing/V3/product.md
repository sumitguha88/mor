# Concept: Product

## Canonical
product

## Type
entity

## Aliases
- paint product
- finished good

## Definition
A product is a market-facing paint item that is either manufactured on a production line or received as an imported finished good for storage and downstream distribution.

## Related
- type: contains
  concept: raw material
- type: distributed_via
  concept: regional depot

## Attributes
- product category
- package size
- brand
- manufacturing status

## ExampleQueries
- which raw materials are contained in a product
- what category does a product belong to
- is a product manufactured or imported

## Tags
- product
- finished good
- catalog

## Synonyms
- sellable item
- stock keeping unit

## Notes
Products may be made internally or imported, but both ultimately flow through finished goods storage and outbound distribution.

## Constraints
- must belong to a product category
- must be traceable to manufacturing or import source

## QueryHints
- boost: finished good
- boost: product category

## AnswerRequirements
- definition
- mechanism
- comparison
