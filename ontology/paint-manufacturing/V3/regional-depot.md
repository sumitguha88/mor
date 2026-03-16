# Concept: Regional Depot

## Canonical
regional depot

## Type
entity

## Aliases
- depot
- distribution depot

## Definition
A regional depot is the downstream storage and distribution node that receives finished goods from plants and serves retailers within a geographic area.

## Related
- type: stores
  concept: product
- type: stores
  concept: imported product
- type: ships_to
  concept: retailer

## Attributes
- service region
- depot code
- inventory mix

## ExampleQueries
- where do finished goods go after the plant
- which depot supplies retailers

## Tags
- distribution
- depot
- outbound

## Synonyms
- regional distribution center

## Notes
Regional depots sit between plant outbound storage and retailer delivery.

## Constraints
- must only receive released finished goods
- must dispatch inventory to authorized channels

## QueryHints
- boost: distribution depot
- boost: regional distribution center

## AnswerRequirements
- definition
- mechanism
- comparison
