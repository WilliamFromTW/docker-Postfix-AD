#!/bin/bash
# List of domains
domains=( 
'example.com'
'example2.com'		
)
# file paths and directories
dkim="`pwd`/opendkim"
mkdir -p $dkim
keys="$dkim/keys"
keyfile="$dkim/KeyTable"
signfile="$dkim/SigningTable"
trustfile="$dkim/TrustedHosts"
spffile="$dkim/spfs.txt"
# Set Ipv6 and Ipv4 addresses for the server here
ipv4=""
ipv6=""
# loopback addresses for the server
loop=( localhost 127.0.0.1 )
function loopback {
        for back in "${loop[@]}"
        do
                if ! grep -q "$back" "$trustfile"; then
                        echo "$back" >> "$trustfile"
                fi
        done
}
# Check for files and create / write to them if they dont exist
if [ ! -d "$keys" ]; then
        mkdir "$keys"
fi
if [ ! -f "$keyfile" ]; then
        touch "$keyfile"
fi
if [ ! -f "$signfile" ]; then
        touch "$signfile"
fi
if [ ! -f "$trustfile" ]; then
        touch "$trustfile"
        loopback
else
        loopback
fi
if [ ! -f "$spffile" ]; then
        touch "$spffile"
else
        rm -rf "$spffile"
        touch "$spffile"
fi
if [ ! -z "$ipv6" ]; then
        if ! grep -q "$ipv6" "$trustfile"; then
                echo "$ipv6" >> "$trustfile"
        fi
fi
if [ ! -z "$ipv4" ]; then
        if ! grep -q "$ipv4" "$trustfile"; then
                echo "$ipv4" >> "$trustfile"
        fi
fi
# Generate keys and write the spfs records we need for each domain to one file
for domain in "${domains[@]}"
do
        keydir="$keys/$domain"
        default="$keydir/default.txt"
        if [ ! -d "$keydir" ]; then
                mkdir $keydir
        fi
        cd $keydir
        opendkim-genkey -r -d $domain
        chown opendkim:opendkim default.private
        #key="default._domainkey.$domain $domain:default:$keydir/default.private"
		key="default._domainkey.$domain $domain:default:/etc/opendkim/keys/$domain/default.private"
        sign="*@$domain default._domainkey.$domain\n"
        trust="$domain"
        spf="$(cat $default)"
        # Check only the last line against the spf file as the first line is always the same
        spflast="$(tail -1 $default)"
        if ! grep -q "$key" "$keyfile"; then
                echo "$key" >> "$keyfile"
        fi
        if ! grep -q "$sign" "$signfile"; then
                sign="*@$domain default._domainkey.$domain"
                echo "$sign" >> "$signfile"
                sign="$domain default._domainkey.$domain"
                echo "$sign" >> "$signfile"				
        fi
        if ! grep -q "$trust" "$trustfile"; then
                echo "$trust" >> "$trustfile"
        fi
        if ! grep -q "$spflast" "$spffile"; then
                echo "$spf" >> "$spffile"
        fi
done

