# Concept: Supplier

## Canonical
supplier

## Type
entity

## Aliases
- vendor
- source supplier

## Definition
A supplier is the external business entity that provides raw materials and, in some cases, imported finished products into the paint manufacturing network.

## Related
- type: supplies
  concept: raw material
- type: supplies
  concept: imported product

## Attributes
- supplier code
- approval status
- supply category
- region

## ExampleQueries
- who supplies a raw material
- which supplier provides imported products

## Tags
- supplier
- procurement
- supply chain

## Synonyms
- source partner

## Notes
Suppliers support both manufacturing inputs and direct import finished goods.

## Constraints
- must be approved before supply
- must support traceability for supplied items

## QueryHints
- boost: vendor
- boost: approved supplier

## AnswerRequirements
- definition
- mechanism
- comparison
