// Command notecheck verifies an ISCC-Log checkpoint with the Go reference
// signed-note tooling (the same code paths Tessera fsck uses). It reads the
// verifier key from --vkey and the full checkpoint text from stdin, then runs
// transparency-dev/formats/note.NewVerifier + golang.org/x/mod/sumdb/note.Open.
// On success it prints "OK <name> <size>"; otherwise it exits non-zero.
package main

import (
	"flag"
	"fmt"
	"io"
	"os"

	f_note "github.com/transparency-dev/formats/note"
	"golang.org/x/mod/sumdb/note"
)

func main() {
	vkey := flag.String("vkey", "", "verifier key string (name+hash+base64)")
	flag.Parse()
	if *vkey == "" {
		fmt.Fprintln(os.Stderr, "missing --vkey")
		os.Exit(2)
	}
	v, err := f_note.NewVerifier(*vkey)
	if err != nil {
		fmt.Fprintf(os.Stderr, "bad vkey: %v\n", err)
		os.Exit(2)
	}
	body, err := io.ReadAll(os.Stdin)
	if err != nil {
		fmt.Fprintf(os.Stderr, "read stdin: %v\n", err)
		os.Exit(2)
	}
	n, err := note.Open(body, note.VerifierList(v))
	if err != nil {
		fmt.Fprintf(os.Stderr, "note.Open failed: %v\n", err)
		os.Exit(1)
	}
	if len(n.Sigs) == 0 || len(n.UnverifiedSigs) != 0 {
		fmt.Fprintf(os.Stderr, "unexpected signatures: verified=%d unverified=%d\n", len(n.Sigs), len(n.UnverifiedSigs))
		os.Exit(1)
	}
	fmt.Printf("OK %s\n", n.Sigs[0].Name)
}
