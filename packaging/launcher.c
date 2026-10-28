/* Relocatable CLI entry point; the shipped CPython preserves payload-hook support. */
#include <mach-o/dyld.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

int main(int argc, char **argv) {
    char raw[PATH_MAX], executable[PATH_MAX], python[PATH_MAX], entry[PATH_MAX];
    uint32_t size = sizeof(raw);
    if (_NSGetExecutablePath(raw, &size) || !realpath(raw, executable)) {
        perror("Cannot locate c100x");
        return 1;
    }
    char *slash = strrchr(executable, '/');
    if (!slash) return 1;
    *slash = '\0';
    if (snprintf(python, sizeof(python), "%s/support/python/bin/python3", executable) >= sizeof(python)
        || snprintf(entry, sizeof(entry), "%s/support/app/classe100x/entrypoint.py", executable) >= sizeof(entry)) {
        fputs("Bundle path is too long\n", stderr);
        return 1;
    }
    char **args = calloc((size_t)argc + 4, sizeof(char *));
    if (!args) return 1;
    args[0] = python;
    args[1] = "-I";
    args[2] = "-B";
    args[3] = entry;
    for (int i = 1; i < argc; i++) args[i + 3] = argv[i];
    execv(python, args);
    perror("Cannot start bundled Python; keep c100x and support together");
    return 1;
}
