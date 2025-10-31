# ISCC - Discovery Protocol - Concept

## \*Digital signing, timestamping, and content based discovery of actors and metadata, powered by ISCC and a neutral

protocol.\*

**Date**: 2025-09-23 **Status**: Draft **Author**: Titusz Pan **Email**:
[tp@iscc.io](mailto:tp@iscc.io) **PoC**:
[https://github.com/iscc/iscc-hub](https://github.com/iscc/iscc-hub) **Sandbox**:
[https://sb1.iscc.id](https://sb1.iscc.id)

# Introduction

The first edition of ISO 24138:2024 specifies the syntax, structure, and initial algorithms for the
International Standard Content Code (ISCC).

An ISCC-CODE is a deterministically generated data descriptor (fingerprint) that applies to a
specific piece of digital content and supports similarity based clustering. Anyone can generate an
ISCC-CODE using the open-source reference implementation or any other application conforming to the
provisions of ISO 24138:2024.

However, an ISCC-CODE describes only the digital manifestation itself. It makes no assumptions about
any related copyrightable work, associated actors, or other metadata. Additionally, ISO 24138:2024
does not define any methods for a global and interoperable discovery of such information based on
ISCC-CODEs.

This document introduces the **ISCC Discovery Protocol (IDP)**. The proposed protocol enables
sector-specific or jurisdiction-specific registries to coexist and mutually benefit through seamless
interoperability and efficient content-based discovery of metadata.

The protocol achieves this by transparently recording who declared what content at what time and
where to find related metadata and services. These “Declaration Events” are identified by the newly
introduced and globally unique \*\*ISCC-ID \*\*s. ISCC-IDs can be resolved to external registries
that provide metadata.

The protocol supports self-sovereign signing and timestamping of ISCC declarations, and open
information discovery.

# 

# Terminology & glossary

**ISCC** Any ISCC-CODE, ISCC-UNIT or ISCC-ID

**ISCC-BODY** The actual payload of an ISCC, similarity preserving compact binary code, hash or
timestamp

**ISCC-CODE** An ISCC-HEADER + ISCC-BODY where the ISCC-BODY is a sequence of multiple ISCC-UNIT
BODYs calculated using multiple different algorithms

**ISCC-UNIT** An ISCC-HEADER + ISCC-BODY where the ISCC-BODY is calculated using one specific
algorithm

**ISCC-ID** A globally unique, owned, compact identifier with an ISCC-BODY composed of a 52-bit
microsecond timestamp and a 12-bit HUB-ID of the issuing ISCC-HUB server

**ISCC-HEADER** Self describing header section of all ISCCs composed of MainType, SubType, Version,
Length

**ISCC-HUB** An independently operated server that participates in the network of ISCC-HUBs by
running software conformant with the ISCC discovery protocol

**ISCC-GATEWAY** A service that returns a W3C Controlled Identifier Document
([CID](https://www.w3.org/TR/cid-1.0/)) listing available metadata endpoints and services for the
identified content

**ISCC-REGISTRY** A service provider that stores and serves metadata, implements sector-specific
schemas, and offers specialized services for content identified by ISCCs

**ISCC-DECLARATION** The act of publicly declaring an ISCC-CODE by sending a digitally signed
message to an ISCC-HUB

**Hamming distance** Number of differences between two ISCC-CODEs in bits (dis-similiarity)

# Infrastructure Layers

The ISCC Discovery Protocol (IDP) transforms digital content into a gateway for discovery of related
metadata and services. Every piece of content becomes:

- **Self-describing**: Discoverable metadata ecosystem
- **Addressable**: Direct API-like access to services
- **Open**: ISCC-IDs can resolve to multiple services offered bdifferent providers
- **Composable**: Services can build on each other

This enables a post-platform internet where content identity itself becomes the gateway to metadata
and service discovery.

The protocol operates through three functionally separated layers:

![][image1]

## ISCC-HUBs

The foundational timestamping and discovery network. HUBs accept signed ISCC declarations, issue
globally unique ISCC-IDs, maintain transparency logs, and replicate declaration records across the
HUB network based on content similarity. They provide the core infrastructure for content
identification and discovery without storing metadata.

## ISCC-GATEWAYs

The routing and service discovery layer. GATEWAYs provide standardized Controlled Identifier
Documents (CIDs) for ISCC-IDs that enumerate available services and metadata endpoints for the
identified content. They act as intelligent routers, directing queries to appropriate REGISTRIES
based on use case, sector, or service type.

## ISCC-REGISTRIEs

The metadata and service provisioning layer. REGISTRIEs store and serve actual metadata about
content, implement sector-specific schemas, enforce their own trust and verification requirements,
and provide specialized services such as licensing, attribution, or rights management. Existing and
new registries can utilize and interface with the ISCC-HUB network to archive global content base
discoverability and interconnection in an open marketplace for metadata services.

This separation ensures that core infrastructure (HUBs) remains lightweight and neutral, while
allowing sophisticated services and trust models to emerge at the registry layer, with gateways
providing seamless discovery and routing between them.

# Trust Through Transparency

The ISCC Discovery Protocol embraces universal content identification while providing strong
accountability mechanisms:

## Universal Declarations

Any actor may declare any digital content. This openness is intentional—legitimate interests in
content identification extend far beyond traditional rights holders to include libraries, archives,
researchers, distributors, platforms, users, and others. The protocol makes no assumptions about
authorship or rights. It simply creates verifiable records of *who* identified *what* content
*when*.

This universality creates an obvious challenge: multiple parties may make conflicting claims about
the same content. A photographer, stock photo agency, and unauthorized user might all declare the
same image with different metadata and ownership assertions.

## Trust Emerges from Transparency

![][image2]

Rather than attempting to determine "truth" through central authority, the protocol embraces
competing claims as a feature, not a bug. Every claim becomes part of a permanent, transparent
record that enables:

- **Temporal ordering**: Timestamps reveal who made claims when, providing crucial evidence for
  disputes
- **Attribution chains**: Each claim links to a cryptographic identity, creating accountability
- **Evidence attachment**: Claimants can link to supporting documentation, building their case
- **Counter-claims**: Legitimate parties can always respond with their own verifiable claims

This transparency transforms potential chaos into useful signals. False claims don't disappear -
they remain visible, attributed to their source. Over time, trust develops through multiple signals:

- **Actor Reputation**: Public keys accumulate reputation over time through consistent, accurate
  ISCC declarations
- **Registry Reputation**: Operators establish trust through transparent policies and reliable
  service
- **Network Accountability**: Participants can flag malicious actors, enabling blocklists of
  problematic public keys or hubs.
- **Authoritative Presence**: Publishers and creators can establish verified identities (via DIDs or
  domain-linked keys) that become recognizable trust anchors

This open-yet-accountable model creates an open competition for trust that balances broad
participation with verifiable attribution, enabling legitimate stakeholders to build reputation
while exposing bad actors through transparent records.

## Conflict Detection and Resolution

A single ISCC-CODE may be declared multiple times across the network by different actors creating
unique but matchable ISCC-IDs. This multiplicity enables rich discovery while the permanent audit
trail ensures accountability, creating strong incentives for accurate declarations.

The protocol's transparency naturally exposes conflicting claims about content. When multiple
parties declare the same content with different metadata or ownership assertions, these conflicts
become immediately visible globally.

The permanent timestamp ordering provides crucial evidence for dispute resolution - showing who made
which claims when. While the protocol itself remains neutral and doesn't adjudicate disputes, it
provides the verifiable audit trail that legal systems, arbitrators, or community governance
mechanisms need to resolve conflicts. This "sunlight as disinfectant" approach ensures that all
claims about content are public, timestamped, and permanently attributable.

Recognizing that both centralized authorities and decentralized systems only approximate truth, is a
strength, not a weakness. It creates a system that adapts to different contexts, jurisdictions, and
evolving norms while maintaining the transparency needed for accountability.

## Content Moderation and Redaction

While maintaining transparency, ISCC-HUBs MAY implement content moderation mechanisms:

**Redaction Capability**:

- HUBs MAY mark declarations as "redacted" without removing them from the log
- Redacted declarations remain in the log but are excluded from public queries
- Redaction reasons MAY include legal compliance, abuse prevention, or terms violation

**Implementation Requirements**:

- Redaction MUST NOT delete events from the append-only log
- Redacted content MUST remain verifiable through checkpoint proofs
- HUBs MUST document their redaction policies publicly
- Appeals or dispute resolution processes SHOULD be available

# ISCC-ID

![][image3]

The ISCC-ID is a new primitive within the ISCC System. ISCC-IDs are globally unique timestamp based
identifiers minted and digitally signed by independent ISCC-HUBs. Each valid ISCC-ID is issued as a
verifiable credential, binding together the following critical information:

- **WHO**: The public key of the ISCC-ID owner (declarer) and issuer (hub).
- **WHEN**: A timestamp (proof of existence), signed by the ISCC-HUB.
- **WHERE**: A URL location where associated metadata/services can be discovered.
- **WHAT**: The digital content represented by an ISCC-CODE and a secure hash.

## Structure & Format of the ISCC-ID:

![][image4]

The ISCC-ID is an ISCC-encoded 64-bit content identifier constructed from a timestamp and a hub-id:

- First 52 bits: UTC time in microseconds since UNIX epoch (1970-01-01T00:00:00Z)
- Last 12 bits: ID of the timestamping server (0–4095)
- Scheme Prefix: `ISCC:`
- Base32-Encoded concatenation of:
  - 16-bit ISCC-HEADER:
    - MAINTYPE = "0110" (ISCC-ID)
    - SUBTYPE = "0000" (REALM)
    - VERSION = "0001" (V1)
    - LENGTH = "0000" (64-bit, no counter)
  - 64-bit ISCC-BODY:
    - 52-bit timestamp: Microseconds since epoch (1970-01-01T00:00:00Z)
    - 12-bit server-id: Server-ID (0–4095) of the issuing ISCC-HUB

With this structure:

- A single HUB can issue up to one million timestamps per second until the year 2112
- The system supports up to 4096 timestamp servers (IDs 0–4095)
- Timestamps are globally unique and support total ordering in both integer and base32hex
  representations
- The theoretical maximum throughput per REALM is ~4 billion unique timestamps per second

For database storage efficiency, ISCC-HUBs MAY store the ISCC-ID as 8-byte binary data containing
only the 64-bit ISCC-BODY, omitting the 16-bit ISCC-HEADER. The ISCC-HEADER can be deterministically
reconstructed when converting back to the string representation. This optimization reduces storage
requirements by 20% while maintaining full compatibility with the ISCC-ID format.

# ISCC-HUBs

ISCC-HUBs are servers that provide distributed ISCC-ID issuing, content timestamping, content based
search services and initial entry points for metadata discovery. ISCC-HUBs MUST publish an auditable
contiguous transparency log of all declaration events and provide public access to those logs in
bulk and at no cost.

ISCC-HUBs do not store or provide specific metadata about digital content aside from optionally
resolving to a single entrypoint (GATEWAY URL) per ISCC-ID for further use-case of sector-specific
metadata discovery.

Service policies for ISCC declarations (permissions, fees, ...) are at the discretion of individual
ISCC-HUBs implementation and operator.

## Event Log Structure

ISCC-HUBs MUST maintain an append-only event log with the following properties:

- **Gapless sequence numbers**: Each event receives a monotonically increasing sequence number
  without gaps, enabling detection of missing events
- **Event types**: Support for CREATED, UPDATED, and DELETED event types to track the full lifecycle
  of declarations
- **Event hash**: Each event includes a Blake3 hash of its canonicalized content for integrity
  verification

The event log serves as the authoritative source of truth, with all other data structures being
derivable from it.

## The ISCC-HUB-LIST

A decentralized list of up to 4096 authoritative ISCC-HUBs.

The ISCC-HUB-LIST (IHL) is the authoritative list of HUBs (servers) that participate in the network.
The IHL is at the core of the protocol and enables the operation of a scalable, reliable, and
efficient network. Additionally, it plays an important role in multiple areas such as governance,
trust, transparency, neutrality, security, and long-term sustainability. The IHL is at the root of
the protocol because:

- URLs/IPs and public keys of HUBs must be known to all participants for efficient declaration,
  replication, and discovery of ISCCs, actors, and metadata services.
- The ID space for ISCC-HUBs is limited to 4096 HUBs
- Frequent HUB joins/leaves are costly in terms of replica reorganization
- The IHL requires high service availability and long-term data persistence
- The protocol targets a stable network with a low-to-moderate HUB churn rate

Management of the IHL itself is a centralization risk and requires high security but low transaction
volume. As such it is an ideal candidate for a blockchain-based Smart Contract. HUB registration
should be permissionless but somewhat costly to minimize node churn and avoid HUB-ID squatting.

## HUB-LIST Registration

**Public Key Requirements**:

HUBs SHOULD optimize their public keys for uniform distribution across the 256-bit ID space. This
ensures balanced load distribution.

**HUB Registration Process**:

1. Generate Ed25519 keypair optimized for ID space coverage
2. Register public key and API endpoint with authoritative smart contract
3. Begin accepting declaration requests

## Log Transparency and Verification

ISCC-HUBs MUST provide cryptographic auditing and verification of their event logs by anchoring
their declaration log state at least once daily through a tamper-proof **Checkpoint System** that
prove historical log states and enable dispute resolution. Cryptographic checkpoints include:

- Merkle tree root of all events since the last checkpoint
- Previous checkpoint hash for chain continuity
- Timestamp from an external authority (RFC3161 or OpenTimestamps)
- Digital signature from the hub's private key

The checkpoint system enables efficient verification of log integrity without accessing the entire
event history. Clients can verify any event's inclusion by checking its Merkle proof against the
nearest checkpoint.

## Hub Operational Modes

ISCC-HUBs MAY operate in different modes based on deployment requirements:

**Open Mode**:

- Any actor can declare any content without prior authorization
- Implements the universal declaration principle described in this document

**Permissioned Mode**:

- Only pre-authorized public keys can make declarations
- HUBs maintain a list of authorized keys
- Suitable for enterprise or consortium deployments
- Does not affect the global discovery network

**Hybrid Mode**:

- Combines open and permissioned access
- Certain operations require authorization
- Public declarations allowed with restrictions (rate limits, duplicate filters)

# Content Declaration

![][image5]

## ISCC-CODE Declaration Flow:

1. Create a self-sovereign account by generating an Ed25519 keypair (no third-party sign-up
   required).
2. Create an ISCC-CODE for a digital asset you want to declare
3. Create an IsccNote (JSON object) including the ISCC-CODE, datahash, nonce, timestamp and optional
   gateway URL and extended ISCC-UNITs.
4. Sign the IsccNote with your Ed25519 keypair ( see:
   [https://github.com/iscc/iscc-crypto](https://github.com/iscc/iscc-crypto))
5. Submit the IsccNote to the ISCC-HUB of your choosing

**The ISCC-HUB will then**:

- Verify the submitted IsccNote
- Create and record a unique ISCC-ID based on the current time and the HUB-ID
- Create, digitally sign, and return an **IsccReceipt** including the original IsccNote

The IsccReceipt is a Verifiable Credential that binds the WHO, WHEN, WHERE, WHAT and is replicated
to multiple ISCC-HUBs for permanent storage and high availability.

## IsccNote Structure

An IsccNote is a digitally signed JSON object containing all information required to declare an
ISCC-CODE at a given ISCC-HUB. All optional fields may be omitted in an IsccNote but if provided
they MUST not be null or empty strings or empty arrays.

**Properties**

**iscc_code** (required): The ISCC-CODE that describes the digital content

**datahash** (required): A cryptographic hash of the content (256-bit hex-encoded blake3 multihash
with prefix `1e20`)

**nonce** (required): 128-bit hex-encoded random value where the first 12 bits MUST match the ID
(0-4095) of the target ISCC-HUB to prevent cross-server replay attacks. HUBs MUST reject IsccNotes
where the nonce prefix does not match their HUB-ID. The nonce MUST be unique per HUB to prevent
replay attacks.

**timestamp** (required): RFC 3339 formatted timestamp in UTC with millisecond precision (e.g.,
"2025-08-04T12:34:56.789Z"). The 'Z' suffix MUST be used to indicate UTC. This timestamp indicates
when the IsccNote was created and signed by the declaring party. HUBs MUST reject IsccNotes with
timestamps outside of ±10 minutes from the HUB's current time.

**Note**: While client timestamps use millisecond precision for cross-platform compatibility, the
ISCC-ID contains a microsecond-precision timestamp generated by the HUB at declaration time.

**gateway** (optional): URL or [uritemplate](https://datatracker.ietf.org/doc/html/rfc6570) pointing
to a GATEWAY for metadata and service discovery

**units** (optional): Array of extended similarity-preserving ISCC-UNITs excluding the Instance-Code
(can be derived from datahash)

**metahash** (optional): Blake3 hash of
[seed metadata](https://ieps.iscc.codes/iep-0002/#62-meta-hash-processing) (256-bit hex-encoded
multihash with prefix `1e20`). When present, this creates a cryptographic commitment to the exact
metadata state at declaration time, allowing external registries to store mutable or deletable
metadata while maintaining temporal integrity.

**signature** (required): A digital signature for the IsccNote request

## IsccSignature Structure

A digital signature as specified in the
[ISCC Signature Specification](https://crypto.iscc.codes/iscc-sig-spec/)

**Properties**

**version** (required): Signature format version (currently `ISCC-SIG v1.0`)

**pubkey** (required): Ed25519 public key in multibase format

**proof** (required): EdDSA signature in multibase format

**controller** (optional): DID identifying the key controller

**keyid** (optional): Specific key identifier within controller document

## Gateway handling

ISCC-HUBs have flexibility in gateway URL handling:

1. **Redirect Mode**: HUBs MAY simply redirect resolution requests to the gateway URL, allowing
   external services to handle all metadata and CID document generation
2. **Gateway Mode**: HUBs MAY act as gateways themselves, generating and serving W3C CID documents
   directly
3. **Hybrid Mode**: HUBs MAY selectively serve some metadata while redirecting to external gateways
   for specialized services

Gateway URLs can be either URLs or URI Templates as defined in
[RFC 6570](https://datatracker.ietf.org/doc/html/rfc6570). If the gateway property is provided with
an IsccNote its value will be stored in the declaration log and counter signed in the IsccReceipt.
When resolving an ISCC-ID the gateway value will be used to construct the forwarding target URL.

**URL handling**

If the gateway value is an URL the ISCC-HUB will redirect to that url.

**URI Template handling**

The gateway field supports RFC 6570 URI Templates for flexible URL patterns. Available variables
are:

- `{iscc_id}` - The ISCC-ID assigned by the HUB
- `{iscc_code}` - The ISCC-CODE from this note
- `{datahash}` - The content's blake3 hash

Example:

`https://api.example.com/v1/content/{iscc_id}`

Service deep links append to the URL or expanded template:

- Template: `https://gateway.example.com/{iscc_id}`
- Deep link: TdmInfo
- Final URL: `https://gateway.example.com/maighfecjmopmiab?serviceType=TdmInfo`

**IsccNote example with gateway**:

```json
{
    "iscc_code": "ISCC:KACT46A6S3L5XTH3O2UXRHPKZOTRV2QZ2UDAEVWVWOACDIKE4HHI7VA",
    "datahash": "1e208021a144e1ce8fd4ecb2c7660d712b0e6818926bf2e3bb4930d54b5b23ed304d",
    "nonce": "000faa3f18c7b9407a48536a9b00c4cb",
    "gateway": "https://gateway.example.com",
    "units": [
        "ISCC:AADZH265WE3KJOSR5K67QJEF5JHLF2REJJYVI4ZYKJ727JU2ZX2AHNQ",
        "ISCC:EADUZ5XBKQCWGG4HYIKX7CNPQMFTPTWEUCQLXFJWC25TKM645KYUSNQ",
        "ISCC:GADZFVRM53JZBN7XOOT3Y6FL372G2GY6PEKRY43JIJ6KV4GH5P7NN4A"
    ],
    "signature": {
        "version": "ISCC-SIG v1.0",
        "controller": "did:web:publisher.example.com",
        "keyid": "signing-key-2025",
        "pubkey": "z6MkhQLS6HMEd8Tc6sBtY1LFutKSt69K69g77asCKXAZsAT1",
        "proof": "zYsDddLFwrhcw8YfbmTQXCSiZYu5BEyCp1ULWERuvgVEVunoCiwxe5n8KF3QPA9s7W4z9eM8dUbtQML5y7mqjCDr"
    }
}
```

The HUB validates all fields, verifies the signature, creates a unique ISCC-ID timestamp for
permanent record in the declaration log, and issues an IsccReceipt to the requester.

# Content-Aware Replication & Discovery

![][image6]

Global content discovery is enabled through distributed replication based on content similarity:

## Replication Strategy

Each HUB will replicate declaration records to other HUBs whose public keys are "nearest" in the
256-bit ID space:

- **ISCC-ID Distribution**: Full declaration log entries replicate to HUBs nearest to
  `hash(ISCC-ID)`, ensuring uniform distribution and preventing temporal clustering
- **Unit-Based Distribution**: Each ISCC-UNIT replicates full declaration log entries to HUBs
  nearest to its raw ISCC-BODY value, clustering similar content on the same HUBs
- **BLAKE3-Based Distribution**: Each declaration log entry is replicated to HUBs nearest to the
  BLAKE3 hash of the identified content.
- **Replica Selection**: For each replication target, select the nearest HUB by Hamming distance
  that hasn't already been selected for this entry

**Discovery Benefits**: This design enables:

- **Resilient Lookup**: Any ISCC-ID can be found by querying the issuing HUB and HUBs near
  `hash(ISCC-ID)`
- **Similarity Search**: Content-similar ISCCs naturally cluster on the same HUBs via their unit
  bodies
- **Load Distribution**: Public keys uniformly distributed across the ID space ensure balanced
  storage
- **Replication Factor**: declaration entries are replicated to at least three and up to six HUBs
  depending on the number of UNITs of the declared ISCC-CODE

This content-aware replication model transforms the HUB network into a global, similarity-preserving
index of all declared content.

## ISCC-ID based lookup

Given a known ISCC-ID any actor can determine the issuing HUB and discover associated metadata by:

1. decoding the HUBs HUB-ID from the ISCC-ID
2. resolving the network address of the HUB server from the HUB-LIST
3. issuing a REST API call to the root endpoint of the responsible HUB
4. following the gateway URL provided in the response from the HUB

If the issuing HUB is out of operation, the actor can calculate a priority list of fallback HUBs
specific to the given ISCC-ID.

## ISCC-CODE based discovery

Given some digital content an actor can generate the ISCC-CODE and retrieve declaration records with
identical or similar ISCC-UNITs from HUBs and discover actors and associated metadata.

## BLAKE3 based discovery

Given some digital content an actor can calculate the BLAKE3 cryptographic hash of that content and
determine the responsible replication HUB to retrieve declaration records for exactly that content.

# Gateways

A gateway is an HTTP endpoint that acts as a resolver to different services related to the content
identified by a given ISCC-ID - such as sector or use-case specific metadata lookup or other
services.

## Gateway Response Format

Gateways MUST return responses conforming to the [W3C CID](https://www.w3.org/TR/cid-1.0/)
specification. This standardized format ensures interoperability across different implementations
and use cases.

A GATEWAY response for an ISCC-ID follows this structure:

```json
{
    "@context": [
        "https://www.w3.org/ns/cid/v1",
        "https://purl.org/iscc/context/v1"
    ],
    "id": "<resolver-url>/<iscc-id>",
    "controller": "<did-of-iscc-id-owner>",
    "service": [
        {
            "id": "#tdm",
            "type": "TdmMetadataService",
            "serviceEndpoint": "<metadata-endpoint-url>"
        }
    ]
}
```

The `controller` field contains the DID of the ISCC-ID owner, derived from either:

- The explicit `controller` provided in the IsccNote signature, or
- A `did:key` derived from the signature's public key if no controller was specified

Each service type would have a defined schema for its `serviceEndpoint` structure.

## Core Metadata Service (Recommended)

GATEWAYs SHOULD include `IsccCoreMetadata` in the CID service list to enable efficient discovery,
disambiguation, and rich client-side presentation of search results:

```json
{
    "id": "#core",
    "type": "IsccCoreMetadata",
    "serviceEndpoint": {
        "name": "<content-title>",
        "description": "<brief-description>",
        "meta": "<data-uri-encoded-sector-kernel-metadata>",
        "thumbnail": "<data-uri-or-url>"
    }
}
```

This enables HUB search interfaces to dynamically retrieve and display essential metadata by
fetching CID documents from gateway URLs. Gateways SHOULD configure appropriate CORS headers to
support browser-based access. Extended or sensitive metadata SHOULD be accessed through external
service endpoints.

## Service Deep Linking

Gateways MUST support fragment-based service selection (`#service-id`) returning the specified
service object from the CID document. Gateways MAY additionally support path-based service routing
(`/service-type`) for direct service access.

**Fragment-based** (required): `<gateway-url>/<iscc-id>#tdm`

- Returns the service object with id="#tdm" from the CID document
- Works with static hosting, no server logic required

**Path-based** (optional): //tdm

- May redirect to the service's serviceEndpoint URL
- May proxy the request with additional authentication
- May return a service-specific response format

When using URI templates in the IsccNote gateway field, service paths append after template
expansion:

- Template: [https://gateway.example.com/{iscc_id}](https://resolver.example.com/%7Biscc_id%7D)
- Service path: /tdm
-

Result:
[https://gateway.example.com/ISCC:MAEK2NC3Y5VZ4.../tdm](https://resolver.example.com/ISCC:MAEK2NC3Y5VZ4.../tdm)

Service types and their corresponding endpoint schemas will be defined in the ISCC Service Registry
to ensure consistent implementation across the ecosystem.

# Service Registry

A public registry of metadata schemas and service types would be a valuable addition to the protocol
by ensuring interoperability across the ecosystem:

- **Schema definitions**: JSON Schema/JSON-LD for different metadata types
- **Service type registry**: Standardized service identifiers and endpoints
- **Version management**: Schema evolution with backward compatibility
- **Discovery APIs**: Programmatic access to available schemas and services

# Economic Models and Incentives

To avoid squatting of the namespace there will be an annual fee for running a hub, payable to the
registrar of the namespace. Currently it is estimated to be ~4000 Euro p.a.

**Governance of the ISCC Foundation controlling the namespace and driving standardisation efforts**

The namespace will be governed by the ISCC foundation, collecting the fees for registration of an
ISCC Hub.

The ISCC Foundation plans to set up a directed development fund modeled after the legal contracts
provided by the
[Joint Development Foundation/ a Linux Foundation Fund](https://jointdevelopment.org/) governed by a
steering committee composed of relevant stakeholders of the industry interested to use the ISCC
Discovery Protocol.

There will be a technical charter ensuring that contributions to the codebase will not require a
membership.

Members of the steering committee have voting rights and pay an annual membership fee.

## HUB Operator Business Models

- **Freemium**: Basic ISCC declarations free, premium services (bulk processing, API priority) paid
- **Per-declaration fees**: $0.01-$0.10 per declaration
- **Specialization premiums**: Higher fees for specialized verification services
- **Metadata marketplace**: Revenue sharing from metadata service referrals

## Stakeholder Incentives

- **Publishers**: Reduced DMCA/attribution disputes, new revenue streams
- **AI Labs**: Automated compliance at scale, legal clarity
- **Creators**: Provable ownership, automated royalty distribution

# Security Considerations

**Attack Vectors and Mitigations**:

- **False claims**: Addressed through transparency and counter-claims
- **Sybil attacks**: HUB registration fees and reputation systems
- **Key grinding**: Monitoring for suspicious public key patterns
- **Service availability**: Replication ensures resilience
