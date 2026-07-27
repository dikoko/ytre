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
| [`protocol/`](protocol/) | Network protocol: packet framing, serialization, message catalogue. |

## Index

### Design

- [Auction house](design/auction-system.md) — timed auctions with escrowed
  bidding, buyout, and desk-claim delivery: data model, state machines, fee and
  timer rules, protocol, and client UX.

### Protocol

- [Legacy network protocol (2006)](protocol/LEGACY_PROTOCOL.md) — packet
  structure, encryption, serialization rules, message ID ranges and catalogue.
