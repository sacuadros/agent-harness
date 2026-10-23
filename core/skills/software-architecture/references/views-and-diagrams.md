# Architecture views and diagrams

Use [ISO/IEC/IEEE 42010:2022](https://www.iso.org/standard/74393.html) to keep stakeholders, concerns, viewpoints, and models explicit. Use the [C4 model](https://c4model.com/) when its abstractions fit; it is not mandatory.

## Select by question

| Question | Useful view |
|---|---|
| Who uses or depends on the system? | System context |
| What deployable/runtime units exist? | Container/runtime |
| How does one behavior execute? | Dynamic or sequence |
| Where does data originate and change owner? | Data flow and ownership |
| Where can failure spread? | Failure domains and dependency view |
| How is it deployed and operated? | Deployment/topology |
| What changes during migration? | Current, transition, and target views |

## Diagram rules

- Give every element a concrete name, responsibility, owner, and technology only when verified.
- Label arrows with direction, protocol, data, sync/async behavior, and trust or failure significance when relevant.
- Show external actors and systems at the boundary.
- Distinguish current, transition, and target states.
- Link important elements to source, config, contract, or ADR evidence.
- Keep one diagram focused on one stakeholder question.
- Do not add boxes for imagined future services or layers.

A diagram that cannot answer a stakeholder question should not exist.
