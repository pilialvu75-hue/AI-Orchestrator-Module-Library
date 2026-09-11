# Module Library Architecture

The system has three independent roles with one shared exchange boundary:

```text
Open source / public ecosystems
            |
            v
      [ Researcher ]
            |
            | standard candidate submission
            v
       [ Library ]
        ^        |
        |        | certified assets
        |        v
       [ Cantiere / App Factory ]
```

Equivalent shorthand:

`Cantiere -> Library <- Researcher`

The arrows represent interaction with the Library, not direct coupling between Cantiere and Researcher.

## Library

The Library is the stable reusable-software supply store. It owns:

- capability needs (`catalog/needs.json`);
- candidate intake;
- the Lego connector standard;
- immutable module versions;
- certification/provenance/security metadata;
- the certified catalog.

It does not search the internet and it does not build applications.

## Cantiere

The Cantiere remains part of `Ai-orchestrator-riserva`.

It will eventually:

- turn an approved app plan into a capability shopping list;
- query the Library;
- select only economically useful certified pieces;
- adapt/assemble them through trusted adapters;
- build missing capabilities when reuse is not worthwhile;
- submit newly validated, reusable results back to Library intake.

The Cantiere never needs to know whether a Library asset originally came from the Researcher, another project or a built-in source.

## Researcher

The Researcher is a separate autonomous project/repository/service. It reads the Library needs list and searches external ecosystems continuously/scheduled.

For every need it should:

1. discover credible implementations;
2. normally keep at least two independent candidates when useful;
3. pin exact upstream commit/tag;
4. record license, maintenance, dependencies, security and integration cost;
5. normalize the candidate to the Lego connector contract;
6. submit it to Library `intake/`;
7. never mark it certified by itself.

When all current needs are covered, it cycles back through the list and searches for better, safer, faster or easier-to-integrate alternatives. New Library needs join the same cycle.

## Standard exchange boundary

Both producers — Researcher and Cantiere — submit through the same manifest + connector contract. This is what makes pieces interchangeable like Lego blocks.

Only the Library promotion process can move a candidate from intake into certified modules/catalog.
