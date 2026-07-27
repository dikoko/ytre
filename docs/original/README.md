# Original game — reconstructed documentation

Specifications of how the original Yogurting game worked, written up for the
revival project so its systems can be rebuilt faithfully.

These documents describe **behaviour and formats**, not any particular
implementation. Where a value is stated (a fee rate, a timer, a state code, a
message layout), it is the value the original used and is worth preserving for
authenticity; everything else is left to the implementer.

| Folder | Contents |
|---|---|
| [`design/`](design/) | Game system specifications — rules, data models, state machines, and the UI flows that go with them. |
| [`protocol/`](protocol/) | Server architecture and the network protocol: components, packet framing, serialization, message catalogue. |

## Index

### Design

- [Auction house](design/auction-system.md) — timed auctions with escrowed
  bidding, buyout, and desk-claim delivery: data model, state machines, fee and
  timer rules, protocol, and client UX.
- [Game state schema](design/db/game-state-schema.md) — the live per-character
  database: characters, inventory, quests, episodes, social systems, guilds, the
  auction book and account-scoped premium state, with types, keys, relationships
  and a per-table confidence tag.
- [Static content schema](design/db/static-content-schema.md) — the content
  database the game is authored in: schools and fields, episodes and their
  scoring rules, monsters, the skill trees, item and upgrade-stone types, NPCs
  and dialogue, quests, progression curves, titles, and the live-ops scheduling
  tables — including the shared enumerations every content table uses.

### Protocol

- [Server architecture](protocol/ARCHITECTURE.md) — the server processes and
  what each one owned, service discovery and routing, the authority tier, a
  session end to end, and how the roles map onto modern components. **Start
  here.**
- [Legacy network protocol (2006)](protocol/LEGACY_PROTOCOL.md) — packet
  structure, encryption, serialization rules, message ID ranges and catalogue.
