/* SPDX-License-Identifier: MIT */
/* Minimal guest bootstrap: mount libkrun's root share and run the OCI command. */
#define _GNU_SOURCE
#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <json-c/json.h>
#include <net/if.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mount.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

extern char **environ;

static void stop(int status)
{
    fprintf(stderr, "ASTERINAS_POC_EXIT=%d\n", status);
    fflush(NULL);
    sync();
    /* The host PoC launcher observes the status and tears down the VM. */
    for (;;) pause();
}

static void fail(const char *operation)
{
    perror(operation);
    stop(125);
}

static void directory(const char *path)
{
    if (mkdir(path, 0755) && errno != EEXIST) fail(path);
}

static void mount_fs(const char *source, const char *path, const char *type)
{
    directory(path);
    if (mount(source, path, type, 0, NULL) && errno != EBUSY) fail(path);
}

static struct json_object *field(struct json_object *object, const char *name)
{
    struct json_object *value = NULL;
    json_object_object_get_ex(object, name, &value);
    return value;
}

/* Private bootstrap ABI until Asterinas exports virtio port names in sysfs. */
#define VPORT_GET_NAME _IOR('V', 0, char[128])

static void setup_stdio(void)
{
    int console = open("/dev/hvc0", O_RDWR | O_NOCTTY);
    if (console >= 0) {
        if (setsid() < 0 && errno != EPERM) fail("setsid");
        if (ioctl(console, TIOCSCTTY, 0)) fail("set controlling console");
        for (int stream = 0; stream < 3; ++stream)
            if (dup2(console, stream) < 0) fail("attach console");
        close(console);
        directory("/dev/virtio-ports");
        /* Names arrive asynchronously after DEVICE_READY / PORT_READY.
         * Probe every advertised device, without assuming fixed port numbers. */
        for (unsigned attempt = 0; attempt < 200; ++attempt) {
            int pending = 0;
            for (unsigned port = 0; port < 32; ++port) {
                char path[64], name[128] = {0};
                snprintf(path, sizeof(path), "/dev/vport0p%u", port);
                int fd = open(path, O_RDWR | O_NONBLOCK | O_NOCTTY);
                if (fd < 0) continue;
                if (ioctl(fd, VPORT_GET_NAME, name)) {
                    if (errno == EAGAIN) pending = 1;
                    close(fd);
                    continue;
                }
                int stream = !strcmp(name, "krun-stdin") ? 0 :
                    !strcmp(name, "krun-stdout") ? 1 : !strcmp(name, "krun-stderr") ? 2 : -1;
                if (stream >= 0) {
                    char alias[192];
                    snprintf(alias, sizeof(alias), "/dev/virtio-ports/%s", name);
                    if (symlink(path, alias) && errno != EEXIST) fail("name virtio port");
                    if (fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) & ~O_NONBLOCK) || dup2(fd, stream) < 0)
                        fail("attach virtio port");
                }
                close(fd);
            }
            if (!pending) break;
            usleep(10000);
        }
    } else if (access("/dev/ttyS0", F_OK)) {
        int log = open("/.asterinas.log", O_WRONLY | O_CREAT | O_TRUNC | O_NOFOLLOW, 0600);
        if (log < 0) fail("open guest log");
        if (dup2(log, STDOUT_FILENO) < 0 || dup2(log, STDERR_FILENO) < 0) fail("redirect guest log");
        close(log);
    }
}

int main(void)
{
    setvbuf(stdout, NULL, _IONBF, 0);
    setvbuf(stderr, NULL, _IONBF, 0);
    directory("/newroot");
    if (mount("/dev/root", "/newroot", "virtiofs", 0, NULL)) fail("mount /dev/root");
    if (chdir("/newroot") || chroot(".") || chdir("/")) fail("chroot");
    mount_fs("devtmpfs", "/dev", "devtmpfs");
    mount_fs("proc", "/proc", "proc");
    mount_fs("sysfs", "/sys", "sysfs");
    mount_fs("devpts", "/dev/pts", "devpts");
    mount_fs("tmpfs", "/dev/shm", "tmpfs");
    const char *links[][2] = {
        {"/proc/self/fd", "/dev/fd"}, {"/proc/self/fd/0", "/dev/stdin"},
        {"/proc/self/fd/1", "/dev/stdout"}, {"/proc/self/fd/2", "/dev/stderr"},
    };
    for (size_t i = 0; i < sizeof(links) / sizeof(links[0]); ++i)
        if (symlink(links[i][0], links[i][1]) && errno != EEXIST) fail(links[i][1]);
    setup_stdio();
    puts("Asterinas libkrunfw bootstrap");
    int network = socket(AF_INET, SOCK_DGRAM, 0);
    struct ifreq iface = { .ifr_name = "eth0" };
    if (network >= 0 && !ioctl(network, SIOCGIFADDR, &iface)) {
        char address[INET_ADDRSTRLEN];
        struct sockaddr_in *local = (struct sockaddr_in *)&iface.ifr_addr;
        printf("Network eth0: %s\n", inet_ntop(AF_INET, &local->sin_addr, address, sizeof(address)));
        /* A static guest has no DHCP exchange. Send one packet so passt can
         * learn its Ethernet address before forwarding inbound connections. */
        struct sockaddr_in gateway = { .sin_family = AF_INET, .sin_port = htons(9) };
        inet_pton(AF_INET, "10.0.2.2", &gateway.sin_addr);
        if (sendto(network, "", 1, 0, (struct sockaddr *)&gateway, sizeof(gateway)) < 0)
            perror("announce guest network");
    }
    if (network >= 0) close(network);

    struct json_object *config = json_object_from_file("/.krun_config.json");
    struct json_object *process = config ? field(config, "process") : NULL;
    if (!process) {
        fputs("Missing OCI process configuration\n", stderr);
        stop(125);
    }
    char **command = NULL;
    const char *workdir = "/";
    {
        struct json_object *args = field(process, "args");
        size_t count = args ? json_object_array_length(args) : 0;
        if (!count || count > 4096) {
            fputs("Invalid OCI process.args\n", stderr);
            stop(125);
        }
        command = calloc(count + 1, sizeof(char *));
        if (!command) fail("calloc");
        for (size_t i = 0; i < count; ++i)
            command[i] = (char *)json_object_get_string(json_object_array_get_idx(args, i));
        struct json_object *cwd = field(process, "cwd");
        if (cwd) workdir = json_object_get_string(cwd);
        struct json_object *user = field(process, "user");
        if (user && (json_object_get_int(field(user, "uid")) || json_object_get_int(field(user, "gid")))) {
            fputs("This proof of concept supports guest uid/gid 0 only\n", stderr);
            stop(125);
        }
        struct json_object *env = field(process, "env");
        clearenv();
        for (size_t i = 0; env && i < json_object_array_length(env); ++i) {
            char *item = strdup(json_object_get_string(json_object_array_get_idx(env, i)));
            if (!item || putenv(item)) fail("putenv");
        }
    }
    if (workdir && chdir(workdir)) fail("workdir");
    pid_t child = fork();
    if (child < 0) fail("fork");
    if (!child) {
        execvpe(command[0], command, environ);
        int saved_errno = errno;
        perror(command[0]);
        _exit(saved_errno == ENOENT ? 127 : 126);
    }
    int status;
    while (waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) fail("waitpid");
    }
    stop(WIFEXITED(status) ? WEXITSTATUS(status) : 128 + WTERMSIG(status));
    return 125;
}
