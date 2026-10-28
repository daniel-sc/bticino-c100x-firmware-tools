from classe100x.payload import Context

c = Context()
for target, asset, mode in (("/usr/bin/image-service", "binary", 0o755),
                            ("/etc/image-service.conf", "configuration", 0o600),
                            ("/etc/init.d/image-service", "service", 0o755)):
    c.image.require_file(target, (c.generated / asset).read_bytes(), mode=mode)
c.image.require_symlink("/etc/rc5.d/S99image-service", "../init.d/image-service")
