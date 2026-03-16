# Concept: Finished Goods Warehouse

## Canonical
finished goods warehouse

## Type
entity

## Aliases
- fg warehouse
- finished product warehouse

## Definition
A finished goods warehouse is the storage area where released paint products are held before shipment to regional depots.

## Related
- type: stores
  concept: product
- type: stores
  concept: imported product
- type: ships_to
  concept: regional depot

## Parents
- warehouse

## Attributes
- dispatch status
- pallet capacity
- loading docks

## ExampleQueries
- where are finished goods stored
- where does the fg warehouse ship product

## Tags
- warehouse
- outbound
- finished goods

## Synonyms
- outbound warehouse

## Notes
Both manufactured products and imported finished goods can flow through this warehouse.

## Constraints
- only released finished goods can be shipped
- dispatch inventory must be traceable by lot or batch

## QueryHints
- boost: fg warehouse
- boost: outbound product storage

## AnswerRequirements
- definition
- mechanism
- comparison
