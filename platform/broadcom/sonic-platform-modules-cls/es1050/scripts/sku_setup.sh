#!/bin/bash

update_hwsku()
{
    SKU2=1
    SKU3=2
    SKU4=3
    SKU9=8
    SKU10=9

    echo "Setting up board... "

    hwsku=$(i2cget -f -y 0x1 0x32 0x5B | cut -d 'x' -f2)
    sku=$((0x$hwsku))  # Convert to decimal

    if [ $((sku & 0xF)) -eq $SKU3 ]; then
        pname="ES1050-48CP"
        platform_path="/usr/share/sonic/device/x86_64-cls_es1050_48c-r0"
        touch /usr/local/bin/poe_support
    elif [ $((sku & 0xF)) -eq $SKU2 ]; then
        pname="ES1050-48C"
        platform_path="/usr/share/sonic/device/x86_64-cls_es1050_48c-r0"
    elif [ $((sku & 0xF)) -eq $SKU4 ]; then
        # Nothing to be done
        echo "EG1050-48CP"
        touch /usr/local/bin/poe_support
        return
    elif [ $((sku & 0xF)) -eq $SKU9 ]; then
        platform_path="/usr/share/sonic/device/x86_64-cls_es1010_48c-r0"
        pname="ES1010-48CP"
        touch /usr/local/bin/poe_support
    elif [ $((sku & 0xF)) -eq $SKU10 ]; then
        platform_path="/usr/share/sonic/device/x86_64-cls_es1010_48c-r0"
        pname="ES1010-48C"
    else
        echo "Error: Unknown SKU"
        return
    fi

    hwsku_file="$platform_path/default_sku"
    component_file="$platform_path/platform_components.json"

    echo "$pname t1"
    echo "$pname t1" > "$hwsku_file"
    sed -i "s/<hwsku-name>/$pname/1" $component_file &> /dev/null
}

main()
{
    update_hwsku
}

# Call the main function
main
