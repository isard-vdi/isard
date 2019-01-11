#!/bin/bash

function print_title() {
	echo -e "\n#"
	echo -e "# \033[1;33m$1\033[0m"
	echo -e "#\n"
}

function main() {
	# Create the out directories
	print_title "Creating the out directories"
	original_dir=$(pwd)

	mkdir -p out/i386
	mkdir out/x86_64
	mkdir out/arm32
	mkdir out/arm64


	# Read the configuration 
	# https://stackoverflow.com/questions/5014632/how-can-i-parse-a-yaml-file-from-a-linux-shell-script
	print_title "Reading the configuration file"
	while read -r line; do
		eval $line
	done < <(sed -e 's/:[^:\/\/]/="/g;s/$/"/g;s/ *=/=/g' config.yml)

	# Create a temporary directory and move to it
	tmp_dir="/tmp/ipxe-$RANDOM"
	mkdir $tmp_dir

	# Download the certificate
	# https://serverfault.com/questions/139728/how-to-download-the-ssl-certificate-from-a-website
	print_title "Downloading the HTTPS certificate"
	echo -n \
		| openssl s_client -connect $(echo $base_url | sed -e "s/^http[s]\?\:\/\///g"):443 -showcerts \
		| sed -ne '/-BEGIN CERTIFICATE-/,/-END CERTIFICATE-/p' > "$tmp_dir/cert.pem"

	cd $tmp_dir

	# Clone the iPXE repository and move to the correct directory
	print_title "Clonning the iPXE repository"
	git clone git://git.ipxe.org/ipxe.git
	cd ipxe/src

	# Change the required configurations
	print_title "Applying configuration changes"

	## Enable HTTPS
	sed -ie 's!#undef\tDOWNLOAD_PROTO_HTTPS\t\/\* Secure Hypertext Transfer Protocol \*\/!#define\tDOWNLOAD_PROTO_HTTPS\t\/\* Secure Hypertext Transfer Protocol \*\/!g' config/general.h

	## Add the Reboot command
	sed -ie 's!\/\/#define REBOOT_CMD\t\t\/\* Reboot command \*\/!#define REBOOT_CMD\t\t\/\* Reboot command \*\/!g' config/general.h

	## Add the Power off command
	sed -ie 's!\/\/#define POWEROFF_CMD\t\t\/\* Power off command \*\/!#define POWEROFF_CMD\t\t\/\* Power off command \*\/!g' config/general.h

	## ?TODO?: Add the keyboard layout

	# Create the chain script
	print_title "Creating the chain script"
	echo "#!ipxe
	dhcp
	chain $base_url/pxe/boot" > chain.ipxe

	# Compile the DHCP script
	print_title "Compiling iPXE"
	make bin-i386-pcbios/undionly.kpxe EMBED=./chain.ipxe TRUST=../../cert.pem
	make bin-i386-efi/ipxe.efi EMBED=./chain.ipxe TRUST=../../cert.pem
	make bin-x86_64-pcbios/undionly.kpxe EMBED=./chain.ipxe TRUST=../../cert.pem
	make bin-x86_64-efi/ipxe.efi EMBED=./chain.ipxe TRUST=../../cert.pem
	make bin-arm32-efi/ipxe.efi EMBED=./chain.ipxe TRUST=../../cert.pem
	make bin-arm64-efi/ipxe.efi EMBED=./chain.ipxe TRUST=../../cert.pem

	# Copy the generated files to the original directory
	print_title "Copying the generated files"
	cp bin-i386-pcbios/undionly.kpxe $original_dir/out/i386
	cp bin-i386-efi/ipxe.efi $original_dir/out/i386
	cp bin-x86_64-pcbios/undionly.kpxe $original_dir/out/x86_64
	cp bin-x86_64-efi/ipxe.efi $original_dir/out/x86_64
	cp bin-arm32-efi/ipxe.efi $original_dir/out/arm32
	cp bin-arm64-efi/ipxe.efi $original_dir/out/arm64

	# Move back to the original_dir
	cd $original_dir

	# Remove the temporal directory
	print_title "Cleanup"
	rm -rf $tmp_dir

	# Finish message
	echo -e "\033[0;32m\n#\n#\n# Yay! It has finished!\n#\n#\n\033[0m"
	echo "Generated files:"
	echo -e "  - undionly.kpxe\n"
}

main
