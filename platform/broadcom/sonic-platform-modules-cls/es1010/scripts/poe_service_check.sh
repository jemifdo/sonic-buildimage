#!/bin/bash

poe_sku_check()
{
    # PoE supported SKUs
    SKU3=2
    SKU4=3
    SKU9=8

    hwsku=$(i2cget -f -y 0x1 0x32 0x5B | cut -d 'x' -f2)
    sku=$((0x$hwsku & 0xF)) 

    if [ $sku -eq $SKU3 ] || [ $sku -eq $SKU4 ] || [ $sku -eq $SKU9 ]; then
        systemctl enable cls-poe-manager.service
        systemctl start cls-poe-manager.service
    else
        # PoE not supported on this SKU, therefore cls-poe-manager.service will be deleted.
        rm lib/systemd/system/cls-poe-manager.service 2>/dev/null
    fi
}

main()
{
    poe_sku_check
}

# Call the main function
main
