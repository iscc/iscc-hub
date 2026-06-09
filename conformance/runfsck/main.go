// Command runfsck runs the Tessera fsck integrity check against a tlog-tiles
// log and exits non-zero on any failure. Unlike cmd/fsck (which only logs
// errors via klog), this wrapper surfaces a clean exit code for test gating.
//
// It uses the same code paths as cmd/fsck: an HTTP fetcher, a signed-note
// verifier from transparency-dev/formats/note, and the RFC 6962 leaf hasher
// over the C2SP entry-bundle framing.
package main

import (
	"context"
	"flag"
	"fmt"
	"net/url"
	"os"

	f_note "github.com/transparency-dev/formats/note"
	"github.com/transparency-dev/merkle/rfc6962"
	"github.com/transparency-dev/tessera/api"
	"github.com/transparency-dev/tessera/client"
	"github.com/transparency-dev/tessera/fsck"
)

func leafHasher(bundle []byte) ([][]byte, error) {
	eb := &api.EntryBundle{}
	if err := eb.UnmarshalText(bundle); err != nil {
		return nil, fmt.Errorf("unmarshal: %v", err)
	}
	out := make([][]byte, 0, len(eb.Entries))
	for _, e := range eb.Entries {
		h := rfc6962.DefaultHasher.HashLeaf(e)
		out = append(out, h[:])
	}
	return out, nil
}

func main() {
	storageURL := flag.String("storage_url", "", "Base tlog-tiles URL")
	origin := flag.String("origin", "", "Expected checkpoint origin")
	pubKey := flag.String("public_key", "", "Path to the log's verifier key file")
	flag.Parse()

	u, err := url.Parse(*storageURL)
	if err != nil {
		fmt.Fprintf(os.Stderr, "bad --storage_url: %v\n", err)
		os.Exit(2)
	}
	src, err := client.NewHTTPFetcher(u, nil)
	if err != nil {
		fmt.Fprintf(os.Stderr, "fetcher: %v\n", err)
		os.Exit(2)
	}
	b, err := os.ReadFile(*pubKey)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read public_key: %v\n", err)
		os.Exit(2)
	}
	v, err := f_note.NewVerifier(string(b))
	if err != nil {
		fmt.Fprintf(os.Stderr, "verifier: %v\n", err)
		os.Exit(2)
	}

	f := fsck.New(*origin, v, src, leafHasher, fsck.Opts{N: 1})
	if err := f.Check(context.Background()); err != nil {
		fmt.Fprintf(os.Stderr, "FSCK FAIL: %v\n", err)
		os.Exit(1)
	}
	fmt.Println("FSCK OK")
}
