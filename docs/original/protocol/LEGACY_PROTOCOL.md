# Yogurting Legacy Network Protocol (2006)

This document describes the **original** Yogurting network protocol.
It covers only the legacy 2006 binary protocol.


## Table of Contents

1. [Overview](#overview)
2. [Packet Structure](#packet-structure)
3. [Encryption](#encryption)
4. [Serialization](#serialization)
5. [Data Types](#data-types)
6. [Message ID Ranges](#message-id-ranges)
7. [Common Messages (20000-20999)](#common-messages)
8. [Game Messages (21000+)](#game-messages)
9. [Server-to-Server Messages (10000-10999)](#server-to-server-messages)
10. [Appendix: Complete Message ID List](#appendix-complete-message-id-list)

---

## Overview

- **Era**: 2006 retail client/server
- **Transport**: Raw TCP sockets (Windows IOCP on the server)
- **Encryption**: AES-128-CBC on the packet **body** only (header stays plaintext for routing)
- **Serialization**: Custom binary struct format with 4-byte alignment
- **Header**: 6 bytes (4-byte length + 2-byte message ID)
- **Version**: `MSG_VERSION = 2006101201`

---

## Packet Structure

```
+----------------+----------------+---------------------------+
| Length (4B)    | MsgID (2B)     | Body (variable, AES enc)  |
+----------------+----------------+---------------------------+
```

- **Length**: DWORD (little-endian) — total packet size including header
- **MsgID**: WORD (little-endian) — message type identifier
- **Body**: AES-128 encrypted, custom binary serialization
- The 6-byte header (length + MsgID) is **not** encrypted, so the server can route packets
  without decrypting the body; a boundary check on the length field guards against
  truncated or oversized packets.

---

## Encryption

The packet body is encrypted with **AES-128-CBC**. The cipher uses a fixed 16-byte key
compiled into the client and server:

```cpp
// 16 bytes = 128-bit key  ->  AES-128
const unsigned char _ENC_KEY[16] = {
    0x32, 0x33, 0x31, 0x37, 0x11, 0x14, 0x19, 0xf1,
    0xa2, 0xe1, 0xbe, 0x7a, 0x10, 0x4f, 0x14, 0x0a
};
```

- **Algorithm**: AES-128-CBC
- **Key**: fixed 16-byte `_ENC_KEY` (128-bit)
- **Scope**: packet body only; the 6-byte header is plaintext

> **Not to be confused with CLT file encryption.** The encrypted client **data files**
> (`.clt`) use a *different* scheme: **AES-256-CBC** (Rijndael with a 256-bit key), where
> the 32-byte key is derived via `DCipher::MD5ToEncryptionKey()` — `MD5("TestPWD")`
> rendered as a 32-character mixed-case hex string (case chosen by MSVC `rand()` seeded
> with `srand(19)`), with a 16-byte zero IV. That 256-bit scheme applies to asset/data
> files, **not** to network packets. The network packet body is AES-128.

---

## Serialization

The original protocol uses a custom binary struct serialization with:

- 4-byte struct alignment (`#pragma pack(push, 4)`)
- Little-endian byte order
- Fixed-size wide-character string fields with a compile-time capacity
- Variable-length arrays and lists, length-prefixed

---

## Data Types

### Primitive Types

| Type | Size | Description |
|---------------|------|-------------|
| `BYTE` | 1 | Unsigned 8-bit |
| `WORD` | 2 | Unsigned 16-bit |
| `DWORD` | 4 | Unsigned 32-bit |
| `INT` / `int` | 4 | Signed 32-bit |
| `INT64` | 8 | Signed 64-bit |
| `float` | 4 | Single precision |
| `bool` | 1 | Boolean |
| `YO_COIN` | 8 | Currency (LONGLONG) |

### Core Structures

#### TypeID (4 bytes) — Item/Object Type Identifier

```cpp
struct TypeID {
    union {
        DWORD _id;
        struct {
            TypeSN sn : 24;   // 3 bytes - serial number
            TypeCate cate : 8; // 1 byte - category
        };
    };
};
```

#### UniqueSN (8 bytes) — Unique Serial Number

```cpp
struct UniqueSN {
    union {
        __int64 i64;
        struct {
            int high;  // Server ID
            int low;   // Local serial
        };
    };
};
```

#### _ITEM (12 bytes) — Item Instance

```cpp
struct _ITEM {
    TypeID tid;        // 4 bytes - item type
    union {
        UniqueSN usn;  // 8 bytes - unique ID (for equipment)
        int num;       // 4 bytes - stack count (for consumables)
        YO_COIN money; // 8 bytes - currency amount
    };
};
```

### Item Categories

| Value | Name | Description |
|-------|------|-------------|
| 0 | `ITC_NONE` | None |
| 1 | `ITC_MONEY` | Currency (Taff) |
| 2 | `ITC_BEITEM` | Equipment (Basic Equipment) |
| 3 | `ITC_COITEM` | Consumables |
| 4 | `ITC_QUITEM` | Quest Items |
| 5 | `ITC_ENITEM` | Enchant Items |
| 104 | `ITC_YTITEM` | Yogurting Items |
| 105 | `ITC_BYULITEM` | Byul (Premium) Items |

### Character States

| Value | Name | Description |
|-------|------|-------------|
| 0 | `CHAR_STATUS_NORMAL` | Normal |
| 1 | `CHAR_STATUS_DEAD` | Dead |
| 2 | `CHAR_STATUS_WARP` | Warping |
| 3 | `CHAR_STATUS_REVIVAL` | Reviving |
| 4 | `CHAR_STATUS_INVINCIBLE` | Invincible |
| 5 | `CHAR_STATUS_SIT_GROUND` | Sitting (ground) |
| 6 | `CHAR_STATUS_SIT_CHAIR` | Sitting (chair) |

### Error Codes

| Value | Name | Description |
|-------|------|-------------|
| -1 | `EC_FAIL` | General failure |
| 0 | `EC_SUCC` | Success |
| 10001 | `EC_NO_BYUL_FUNCTION` | Byul feature unavailable |
| 10002 | `EC_BYUL_WAIT_PREV_REQ` | Previous request pending |
| 10005 | `EC_BYUL_PRODUCT_BUY_NO_BYUL` | Insufficient Byul |
| 10006 | `EC_BYUL_PRODUCT_BUY_NO_TAFF` | Insufficient Taff |
| ... | ... | (See `Defs_Msg.h` for complete list) |

---

## Message ID Ranges

| Range | Namespace | Purpose |
|-------|-----------|---------|
| 10000-10999 | `SERVER` | Server-to-Server (SCS, ATS, CAS, CMS) |
| 15000-15999 | `GTSMSG` | Game Tracking Server (Admin/Monitoring) |
| 16000-16999 | `ADMIN` | Admin Tools (GST, SMT) |
| 20000-20999 | `COMMON` | Common Client-Server (version, errors, time) |
| 21000+ | `GAME2` | Game Messages (gameplay, items, NPCs, etc.) |

---

## Common Messages

### Version Check (20001)

**Direction**: Client -> Server

```cpp
struct MSG_CHECK_VERSION_NTF {
    DWORD version;  // Should match MSG_VERSION = 2006101201
};
```

### Error Message (20002)

**Direction**: Server -> Client

```cpp
struct MSG_ERR_MSG_NTF {
    MsgInfo      msgInfo;
    String     msg;
};
```

### World Time Sync (20005)

**Direction**: Server -> Client

```cpp
struct MSG_WORLD_TIME_NTF {
    BYTE season;   // SeasonType (spring, summer, etc.)
    BYTE clock;    // ClockType (time of day)
    DWORD time;    // Milliseconds
};
```

---

## Game Messages

### Enter School/Field (21010)

**Direction**: Server -> Client

```cpp
struct MSG_ENTER_SCS_NTF {
    // Empty - notification only
};
```

### Leave Field (21011)

**Direction**: Server -> Client

```cpp
struct MSG_LEAVE_SCS_NTF {
    // Empty - notification only
};
```

### Enter Episode/Dungeon (21012)

**Direction**: Server -> Client

```cpp
struct MSG_ENTER_ATS_NTF {
    // Empty - notification only
};
```

### Update Item (21001)

**Direction**: Server -> Client

```cpp
struct MSG_GAME_UPDATE_ITEM_NTF {
    Vector<_ITEM> items;
};
```

### Remove Item (21002)

**Direction**: Server -> Client

```cpp
struct MSG_GAME_REMOVE_ITEM_NTF {
    Vector<_ITEM> items;
};
```

### Set HP (21005)

**Direction**: Server -> Client

```cpp
struct MSG_GAME_SET_HP_NTF {
    WORD hp;
};
```

### Set Character State (21007)

**Direction**: Server -> Client

```cpp
struct MSG_GAME_SET_STATE_NTF {
    BYTE grade;      // School year (1-6)
    WORD level;      // Character level
    WORD hpMax;
    WORD pow, spd, skl, luck;
    INT atk, def, hit, flee;
    INT atk_spd, mov_spd, cool_time, crit;
};
```

### NPC Dialog Start (21032)

**Direction**: Client -> Server

```cpp
struct MSG_GAME_NPC_DIALOG_EX_START_NTF {
    int idNpc;
};
```

### NPC Dialog Response (21033)

**Direction**: Server -> Client

```cpp
struct MSG_GAME_NPC_DIALOG_EX_RESPONSE_NTF {
    int idNpc;
    int idDialog;
    int cateCutIn;
    String     sDialogText;
    Vector<DIALOG_SELECTION> vecSelectionText;
    int nTimeOut;
    int idChoiceOnTimeOut;
    BOOL bShowCloseButton;
    BOOL bEnableBgFrameClick;
};
```

### NPC Dialog Select (21036)

**Direction**: Client -> Server

```cpp
struct MSG_GAME_NPC_DIALOG_EX_SELECT_NTF {
    int idDialog;
    BYTE num;       // Selection index
    int idQuest;    // Quest ID if quest-related
};
```

### Object Create (21019)

**Direction**: Server -> Client

```cpp
struct MSG_OBJECT_CREATE_NTF {
    DWORD id;
    _TypeObject type;
    DWORD subid;
    DWORD idCli;
    DWORD shell;
    float posX, posY;
    BYTE direction;
    BYTE visible;
    BYTE usable;
};
```

### Object Types

| Value | Name | Description |
|-------|------|-------------|
| 1 | `OBJ_GUIDE_BOARD` | Information Board |
| 2 | `OBJ_LOBBY` | Episode Lobby |
| 3 | `OBJ_DANCE` | Dance Machine |
| 4 | `OBJ_LOCKER` | Storage Locker |
| 5 | `OBJ_AUCTION` | Auction House |
| 6 | `OBJ_HAIRSHOP` | Hair Salon |

---

## Server-to-Server Messages

These are internal messages exchanged between server processes (SCS, ATS, CAS, CMS, etc.)
and are never sent to clients.

### Server Info (10007)

```cpp
struct MSG_SVR_INFO_NTF {
    WORD snWorld;
    WORD typeServer;
    WORD snServer;
    String     strName;
};
```

### Episode Registration (10009-10012)

Used when SCS (school server) requests ATS (episode server) to create/join an episode
instance.

---

## Appendix: Complete Message ID List

### COMMON (20000-20999)

| ID | Name | Direction | Description |
|----|------|-----------|-------------|
| 20001 | CHECK_VERSION_NTF | C->S | Version check |
| 20002 | ERR_MSG_NTF | S->C | Error message |
| 20003 | PRINT_MSG_NTF | S->C | Print message |
| 20004 | ALERT_MSG_NTF | S->C | Alert dialog |
| 20005 | WORLD_TIME_NTF | S->C | World time sync |
| 20006 | TIME_NTF | S->C | Periodic time sync |

### GAME2 (21000+)

| ID | Name | Direction | Description |
|----|------|-----------|-------------|
| 21001 | GAME_UPDATE_ITEM_NTF | S->C | Item added/updated |
| 21002 | GAME_REMOVE_ITEM_NTF | S->C | Item removed |
| 21003 | GAME_START_REGAIN_NTF | S->C | HP regen start |
| 21004 | GAME_STOP_REGAIN_NTF | S->C | HP regen stop |
| 21005 | GAME_SET_HP_NTF | S->C | Set HP value |
| 21006 | GAME_GENERAL_POTION_NTF | S->C | Potion effect |
| 21007 | GAME_SET_STATE_NTF | S->C | Character stats update |
| 21008 | GOTO_SVR_NTF | S->C | Server redirect |
| 21009 | JOIN_SVR_NTF | C->S | Join server |
| 21010 | ENTER_SCS_NTF | S->C | Enter school field |
| 21011 | LEAVE_SCS_NTF | S->C | Leave school field |
| 21012 | ENTER_ATS_NTF | S->C | Enter episode |
| 21013 | LEAVE_ATS_NTF | S->C | Leave episode |
| 21014 | ESCAPE_REQUEST_NTF | S->C | Escape attempt start |
| 21015 | ESCAPE_ACCEPT_NTF | C<->S | Escape confirmed |
| 21016 | ESCAPE_CANCEL_NTF | C<->S | Escape cancelled |
| 21019 | OBJECT_CREATE_NTF | S->C | Object spawned |
| 21020 | OBJECT_DESTROY_NTF | S->C | Object removed |
| 21021 | OBJECT_SHOW_NTF | S->C | Object visible |
| 21022 | OBJECT_HIDE_NTF | S->C | Object hidden |
| 21023 | OBJECT_USE_REQ | C->S | Use object request |
| 21024 | OBJECT_USE_ANS | S->C | Use object response |
| 21025 | GUIDE_BOARD_ENTER_NTF | S->C | Enter guide board |
| 21026 | GUIDE_BOARD_LEAVE_NTF | C<->S | Leave guide board |
| 21027 | GUIDE_INFO_REQ | C->S | Request guide info |
| 21028 | GUIDE_INFO_ANS | S->C | Guide info response |
| 21031 | LOBBY_STATE_NTF | S->C | Lobby status update |
| 21032 | GAME_NPC_DIALOG_EX_START_NTF | C->S | Start NPC dialog |
| 21033 | GAME_NPC_DIALOG_EX_RESPONSE_NTF | S->C | NPC dialog content |
| 21036 | GAME_NPC_DIALOG_EX_SELECT_NTF | C->S | Select dialog option |
| 21037 | GAME_NPC_DIALOG_EX_EVENT_NTF | S->C | NPC dialog event |
| 21038 | GAME_CALORIE_CONSUME_NTF | S->C | Calorie consumed |
| 21040 | GAME_CALORIE_REGAIN_NTF | S->C | Calorie restored |
| 21043 | GAME_BYUL_SHOP_BEGIN_REQ | C->S | Open premium shop |
| 21044 | GAME_BYUL_SHOP_BEGIN_ANS | S->C | Shop open response |
| 21052 | GAME_BYUL_PRODUCT_LIST_REQ | C->S | Get shop products |
| 21053 | GAME_BYUL_PRODUCT_LIST_ANS | S->C | Shop product list |
| 21054 | GAME_BYUL_PRODUCT_BUY_REQ | C->S | Buy premium item |
| 21055 | GAME_BYUL_PRODUCT_BUY_ANS | S->C | Purchase result |

---

