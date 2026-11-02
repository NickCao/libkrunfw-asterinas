/* SPDX-License-Identifier: MIT */
/* A boot PoC using stock libkrun's C API, not an OCI runtime implementation. */
#define _GNU_SOURCE
#include <libkrun.h>
#include <json-c/json.h>
#include <errno.h>
#include <signal.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static void check(int result, const char *operation)
{
    if (result < 0) {
        fprintf(stderr, "%s failed: %d\n", operation, result);
        exit(125);
    }
}

static void enter_vm(int argc, char **argv, int output)
{
    krun_set_log_level(2);
    int ctx = krun_create_ctx();
    check(ctx, "create context");
    check(krun_set_vm_config(ctx, 1, 1024), "configure VM");
    check(krun_set_root(ctx, argv[1]), "set root");
    check(krun_disable_implicit_console(ctx), "disable multiport console");
    check(krun_disable_implicit_vsock(ctx), "disable TSI/vsock");
    const char *network = getenv("ASTERINAS_PASST_SOCKET");
    if (network) {
        uint8_t mac[] = {0x5a, 0x94, 0xef, 0xe4, 0x0c, 0xee};
        check(krun_add_net_unixstream(ctx, network, -1, mac, COMPAT_NET_FEATURES, 0), "add virtio-net");
    }
    check(krun_set_kernel_console(ctx, "ttyS0"), "select serial console");
    check(krun_add_serial_console_default(ctx, -1, output), "add serial console");
    /* Pass arguments without Linux/Asterinas boot-command-line quoting differences. */
    struct json_object *config = json_object_new_object();
    struct json_object *process = json_object_new_object();
    struct json_object *args = json_object_new_array();
    struct json_object *env = json_object_new_array();
    for (int i = 2; i < argc; ++i)
        json_object_array_add(args, json_object_new_string(argv[i]));
    for (char **item = environ; *item; ++item)
        json_object_array_add(env, json_object_new_string(*item));
    json_object_object_add(process, "args", args);
    json_object_object_add(process, "env", env);
    json_object_object_add(process, "cwd", json_object_new_string("/"));
    json_object_object_add(config, "process", process);
    const char *json = json_object_to_json_string_ext(config, JSON_C_TO_STRING_PLAIN);
    check(krun_fs_add_overlay_file(ctx, "/dev/root", ".krun_config.json",
          (const uint8_t *)json, strlen(json), 0100444, false), "set guest command");
    /* config owns json and remains live until this process/VM exits. */
    check(krun_start_enter(ctx), "start VM");
    exit(125);
}

int main(int argc, char **argv)
{
    if (argc < 3) {
        fprintf(stderr, "Usage: %s ROOT COMMAND [ARG...]\n", argv[0]);
        return 2;
    }
    int stream[2];
    if (pipe(stream)) { perror("pipe"); return 125; }
    pid_t parent = getpid();
    pid_t child = fork();
    if (child < 0) { perror("fork"); return 125; }
    if (!child) {
        prctl(PR_SET_PDEATHSIG, SIGKILL);
        if (getppid() != parent) _exit(125);
        close(stream[0]);
        enter_vm(argc, argv, stream[1]);
    }
    close(stream[1]);
    char buffer[4096];
    int status;
    for (;;) {
        ssize_t size = read(stream[0], buffer, sizeof(buffer));
        if (size < 0 && errno == EINTR) continue;
        if (size <= 0) break;
        if (fwrite(buffer, 1, (size_t)size, stdout) != (size_t)size || fflush(stdout)) {
            kill(child, SIGKILL);
            break;
        }
    }
    close(stream[0]);
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) { perror("waitpid"); return 125; }
    }
    return WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status);
}
