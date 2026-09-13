# Check ancestors above the fixed path root

The independent source reviewer found that the dormant real-file wrapper checked the supplied root and its descendants but not ancestors above that root. A pre-existing junction above the output root could therefore defeat the stated physical-path restriction. The absent real profile prevented any actual access, and no converter qualification has run yet.

Preserve that unexecuted source, then check every component from the volume anchor to the leaf with lstat. Refuse symbolic links and reparse points anywhere in the chain, require existing ancestors to be directories, and permit a missing component only for a new final output leaf. A quiescent private directory remains a precondition against concurrent replacement; the stdlib check is not a Windows handle-based adversarial race guarantee.

Add inert mocked-lstat cases for a junction above the supplied root, a root junction, a symbolic-link leaf, a non-directory ancestor, missing parent, and a valid fresh leaf. No actual filesystem or process-native test is authorized.
