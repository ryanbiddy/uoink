/* Native bundle entry, so codesign can seal the app's main executable. */
#include <mach-o/dyld.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

extern char **environ;

static int clear_environment(void) {
    /* unsetenv compacts environ: recheck this index after every removal. */
    for (size_t i = 0; environ[i];) {
        if (strncmp(environ[i], "DYLD_", 5) != 0) { ++i; continue; }
        char *end = strchr(environ[i], '=');
        if (!end) return -1;
        char *name = strndup(environ[i], (size_t)(end - environ[i]));
        if (!name) return -1;
        int result = unsetenv(name);
        free(name);
        if (result) return -1;
    }
    const char *names[] = {"PYTHONHOME", "PYTHONPATH", "PYTHONSTARTUP",
                           "PYTHONUSERBASE", "PYTHONEXECUTABLE", NULL};
    for (size_t i = 0; names[i]; ++i) {
        if (unsetenv(names[i])) return -1;
    }
    return 0;
}

/* LaunchServices and Xcode add process-serial and NSUserDefaults arguments
 * (-psn_0_123, -NSDocumentRevisionsDebugMode YES). Drop them so a Finder,
 * Dock or Spotlight open still classifies as a plain launch. */
static int user_arguments(int argc, char **argv, char **out) {
    int count = 0;
    for (int i = 1; i < argc; ++i) {
        if (strncmp(argv[i], "-psn_", 5) == 0) continue;
        if (strncmp(argv[i], "-NS", 3) == 0) {
            if (i + 1 < argc && argv[i + 1][0] != '-') ++i;
            continue;
        }
        out[count++] = argv[i];
    }
    return count;
}

int main(int argc, char **argv) {
    char path[PATH_MAX], resolved[PATH_MAX], python[PATH_MAX], script[PATH_MAX];
    uint32_t size = sizeof(path);
    if (_NSGetExecutablePath(path, &size) || !realpath(path, resolved)) {
        perror("Uoink: cannot locate app"); return 1;
    }
    char *part = strrchr(resolved, '/');
    if (!part) return 1;
    *part = 0;
    part = strrchr(resolved, '/');
    if (!part) return 1;
    *part = 0; /* Contents */
    char **user = calloc((size_t)argc + 1, sizeof(char *));
    if (!user) return 1;
    int count = user_arguments(argc, argv, user);
    int plain = count == 0, helper = count > 0 && strcmp(user[0], "--helper") == 0;
    if (snprintf(python, sizeof(python), "%s/Resources/Python/bin/python3", resolved) >= (int)sizeof(python) ||
        snprintf(script, sizeof(script), "%s/Resources/%s", resolved,
                 (plain || helper) ? "uoink_supervisor.py" : "server.py") >= (int)sizeof(script)) return 1;
    if (access(python, X_OK) || access(script, R_OK)) {
        fputs("Uoink installation is incomplete. Reinstall Uoink.app from the DMG.\n", stderr); return 1;
    }
    if (clear_environment()) { perror("Uoink: cannot clear launch environment"); return 1; }
    setenv("PYTHONDONTWRITEBYTECODE", "1", 1); setenv("PYTHONNOUSERSITE", "1", 1);
    char **args = calloc((size_t)count + 6, sizeof(char *));
    if (!args) return 1;
    int n = 0;
    args[n++] = python; args[n++] = "-B"; args[n++] = "-s"; args[n++] = script;
    /* A user opening the app gets a visible window; login startup does not. */
    if (plain) args[n++] = "--show-dashboard";
    /* Login startup requests the helper entry instead of a CLI operation. */
    for (int i = helper ? 1 : 0; i < count; ++i) args[n++] = user[i];
    execv(python, args);
    perror("Uoink: cannot start bundled Python");
    free(args);
    free(user);
    return 1;
}
