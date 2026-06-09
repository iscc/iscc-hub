// Command genkat generates RFC 6962 / tlog-tiles known-answer-test vectors.
//
// It is the authoritative, independent source of truth for the pure-Python
// transparency-log implementation in iscc_hub/merkle.py. Vectors are produced
// with the Go reference libraries (golang.org/x/mod/sumdb/tlog for tree heads
// and proofs, github.com/transparency-dev/tessera/api/layout for tlog-tiles
// paths and partial-tile sizing, and the tessera entry-bundle framing) so the
// Python code can assert byte-equality against them with no Go at test time.
//
// Output is JSON on stdout. The canonical leaf content is record(i) =
// "iscc-log-entry-<i>" so both Go and Python agree on the leaf preimages.
package main

import (
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"sort"

	"github.com/transparency-dev/merkle/rfc6962"
	"github.com/transparency-dev/tessera/api/layout"
	"golang.org/x/mod/sumdb/tlog"
)

// record returns the canonical KAT leaf preimage for index i.
func record(i int64) []byte {
	return []byte(fmt.Sprintf("iscc-log-entry-%d", i))
}

// store accumulates all stored tlog hashes so we can serve a HashReader.
type store map[int64]tlog.Hash

func (s store) reader() tlog.HashReaderFunc {
	return func(indexes []int64) ([]tlog.Hash, error) {
		out := make([]tlog.Hash, len(indexes))
		for i, x := range indexes {
			h, ok := s[x]
			if !ok {
				return nil, fmt.Errorf("missing stored hash %d", x)
			}
			out[i] = h
		}
		return out, nil
	}
}

// build appends records [0, n) and returns the populated hash store.
func build(n int64) store {
	s := store{}
	r := s.reader()
	for i := int64(0); i < n; i++ {
		hs, err := tlog.StoredHashes(i, record(i), r)
		if err != nil {
			panic(err)
		}
		base := tlog.StoredHashCount(i)
		for j, h := range hs {
			s[base+int64(j)] = h
		}
	}
	return s
}

// treeHead returns the RFC 6962 tree head over the first n records.
func treeHead(n int64, s store) tlog.Hash {
	if n == 0 {
		// RFC 6962 empty tree: SHA-256 of the empty string.
		var h tlog.Hash
		copy(h[:], rfc6962.DefaultHasher.EmptyRoot())
		return h
	}
	th, err := tlog.TreeHash(n, s.reader())
	if err != nil {
		panic(err)
	}
	return th
}

// hashTile returns the concatenated 32-byte node hashes of the hash tile at
// tile level L, tile index K, width W (complete perfect-subtree roots at tree
// level L*8).
func hashTile(s store, level, index uint64, width int) []byte {
	out := make([]byte, 0, width*tlog.HashSize)
	for j := 0; j < width; j++ {
		off := int64(index*layout.TileWidth) + int64(j)
		h := s[tlog.StoredHashIndex(int(level*layout.TileHeight), off)]
		out = append(out, h[:]...)
	}
	return out
}

// entryBundle returns the tlog-tiles entry bundle bytes (u16-BE length-prefixed
// records) for bundle index K with the given width.
func entryBundle(index uint64, width int) []byte {
	out := []byte{}
	for j := 0; j < width; j++ {
		i := int64(index*layout.EntryBundleWidth) + int64(j)
		rec := record(i)
		var prefix [2]byte
		binary.BigEndian.PutUint16(prefix[:], uint16(len(rec)))
		out = append(out, prefix[:]...)
		out = append(out, rec...)
	}
	return out
}

func hexstr(b []byte) string { return hex.EncodeToString(b) }

type proofEntry struct {
	Size     int64    `json:"size"`
	Index    int64    `json:"index"`
	LeafHash string   `json:"leaf_hash"`
	Root     string   `json:"root"`
	Proof    []string `json:"proof"`
}

type consistencyEntry struct {
	M     int64    `json:"m"`
	N     int64    `json:"n"`
	RootM string   `json:"root_m"`
	RootN string   `json:"root_n"`
	Proof []string `json:"proof"`
}

func main() {
	sizes := []int64{0, 1, 2, 3, 256, 257, 70000}
	// Sizes for which we emit the full set of tiles + bundles. 70000 is curated.
	fullEmit := map[int64]bool{0: true, 1: true, 2: true, 3: true, 256: true, 257: true}

	roots := map[string]string{}
	hashTiles := map[string]map[string]string{}
	entryBundles := map[string]map[string]string{}

	stores := map[int64]store{}
	for _, n := range sizes {
		s := build(n)
		stores[n] = s
		th := treeHead(n, s)
		roots[fmt.Sprintf("%d", n)] = hexstr(th[:])
	}

	emitTilesBundles := func(n int64, curatedTiles, curatedBundles map[string]bool) {
		s := stores[n]
		tiles := map[string]string{}
		// Hash tiles for every tile level that has complete nodes.
		for level := uint64(0); (uint64(n) >> (level * layout.TileHeight)) > 0; level++ {
			countAtLevel := uint64(n) >> (level * layout.TileHeight)
			numTiles := (countAtLevel + layout.TileWidth - 1) / layout.TileWidth
			for k := uint64(0); k < numTiles; k++ {
				p := layout.PartialTileSize(level, k, uint64(n))
				width := layout.TileWidth
				if p > 0 {
					width = int(p)
				}
				path := layout.TilePath(level, k, p)
				if curatedTiles != nil && !curatedTiles[path] {
					continue
				}
				tiles[path] = hexstr(hashTile(s, level, k, width))
			}
		}
		hashTiles[fmt.Sprintf("%d", n)] = tiles

		bundles := map[string]string{}
		numBundles := (uint64(n) + layout.EntryBundleWidth - 1) / layout.EntryBundleWidth
		for k := uint64(0); k < numBundles; k++ {
			p := layout.PartialTileSize(0, k, uint64(n))
			width := layout.EntryBundleWidth
			if p > 0 {
				width = int(p)
			}
			path := layout.EntriesPath(k, p)
			if curatedBundles != nil && !curatedBundles[path] {
				continue
			}
			bundles[path] = hexstr(entryBundle(k, width))
		}
		entryBundles[fmt.Sprintf("%d", n)] = bundles
	}

	for _, n := range sizes {
		if fullEmit[n] {
			emitTilesBundles(n, nil, nil)
		}
	}
	// Curated subset for the large size-70000 example (spec shape:
	// 273 full + width-112 L0 partial, one full + width-17 L1 partial, width-1 L2 partial).
	emitTilesBundles(70000, map[string]bool{
		layout.TilePath(0, 0, 0):   true, // a full L0 tile
		layout.TilePath(0, 273, 112): true, // partial L0 tile, width 112
		layout.TilePath(1, 0, 0):   true, // a full L1 tile
		layout.TilePath(1, 1, 17):  true, // partial L1 tile, width 17
		layout.TilePath(2, 0, 1):   true, // partial L2 tile, width 1
	}, map[string]bool{
		layout.EntriesPath(0, 0):     true, // full entry bundle
		layout.EntriesPath(273, 112): true, // partial entry bundle, width 112
	})

	// Inclusion proofs.
	inclusionSpecs := []struct {
		size  int64
		index int64
	}{
		{1, 0}, {2, 0}, {2, 1}, {3, 0}, {3, 1}, {3, 2},
		{256, 0}, {256, 255}, {257, 0}, {257, 256}, {257, 128},
		{70000, 0}, {70000, 69999}, {70000, 256}, {70000, 33333},
	}
	inclusion := []proofEntry{}
	for _, spec := range inclusionSpecs {
		s := stores[spec.size]
		p, err := tlog.ProveRecord(spec.size, spec.index, s.reader())
		if err != nil {
			panic(err)
		}
		th := treeHead(spec.size, s)
		lh := tlog.RecordHash(record(spec.index))
		// Self-check against the reference verifier.
		if err := tlog.CheckRecord(p, spec.size, th, spec.index, lh); err != nil {
			panic(fmt.Sprintf("inclusion self-check failed for %v: %v", spec, err))
		}
		ph := make([]string, len(p))
		for i, h := range p {
			ph[i] = hexstr(h[:])
		}
		inclusion = append(inclusion, proofEntry{
			Size: spec.size, Index: spec.index,
			LeafHash: hexstr(lh[:]), Root: hexstr(th[:]), Proof: ph,
		})
	}

	// Consistency proofs (m <= n).
	consistencySpecs := [][2]int64{
		{1, 2}, {2, 3}, {1, 3}, {3, 256}, {256, 257}, {1, 257},
		{257, 70000}, {256, 70000}, {3, 70000}, {70000, 70000},
	}
	consistency := []consistencyEntry{}
	for _, spec := range consistencySpecs {
		m, n := spec[0], spec[1]
		sn := stores[n]
		p, err := tlog.ProveTree(n, m, sn.reader())
		if err != nil {
			panic(err)
		}
		rootM := treeHead(m, stores[m])
		rootN := treeHead(n, sn)
		if err := tlog.CheckTree(p, n, rootN, m, rootM); err != nil {
			panic(fmt.Sprintf("consistency self-check failed for %v: %v", spec, err))
		}
		ph := make([]string, len(p))
		for i, h := range p {
			ph[i] = hexstr(h[:])
		}
		consistency = append(consistency, consistencyEntry{
			M: m, N: n, RootM: hexstr(rootM[:]), RootN: hexstr(rootN[:]), Proof: ph,
		})
	}

	out := map[string]any{
		"description":   "RFC 6962 / C2SP tlog-tiles known-answer-test vectors. Generated by conformance/genkat (Go reference libraries). DO NOT EDIT BY HAND.",
		"record_format": "iscc-log-entry-<i>  (UTF-8, i is the 0-based decimal leaf index)",
		"tile_height":   layout.TileHeight,
		"sizes":         sizes,
		"roots":         roots,
		"hash_tiles":    hashTiles,
		"entry_bundles": entryBundles,
		"inclusion_proofs": inclusion,
		"consistency_proofs": consistency,
	}

	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	// Stable key ordering for maps is handled by encoding/json (sorts string keys).
	_ = sort.Strings
	if err := enc.Encode(out); err != nil {
		panic(err)
	}
}
