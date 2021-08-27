#!/bin/sh

HOSTS=/tmp/dynamic.hosts

help() {
   echo "$(basename "$0"):
   Script para que dnsmasq soporte ddns (DNS dinámico).

Se requiere que dnsmasq contenga la siguiente configuración:

   addn-hosts=$HOSTS
   dhcp-script=$(readlink -f "$0")

   # Comentar o no, dependiendo de si se quiere que el nombre
   # proporcionado por el propio cliente se asocia a la IP
   dhcp-ignore-names
"
}

if [ "$1" = "-h" ]; then
   help
   exit 0
fi

# Argumentos provistos por dnsmasq
ACTION=$1
MAC=$2
IP=$3
NAME=$4

DOMAIN=${DNSMASQ_DOMAIN:+.$DNSMASQ_DOMAIN}

# Registro
# $1: Nivel
# $2: Mensaje.
log() {
   echo "$2" | systemd-cat -p $1 -t "dnsmasq:ddns"
}

# Generador de nombres
generarNombre() {
   echo "$IP" | awk -F. '{print "pc" $3 "-" $4}'
}

# Ya se proporciona un nombre de máquina
# por lo que no es necesario hacer nada.
if [ -n "$NAME" ]; then
   log info "$3: Nombre $NAME ya fijado por dnsmasq"
   exit
fi

# Determina el status de la máquina en el fichero de HOSTS
# 0: La pareja ip/nombre se encuentra en el fichero.
# 1: Se encuentra la ip, pero el nombre es distinto.
# 2: Se encuentra el nombre, pero asociado a otra ip.
# 3: No se encuentran ni nombre ni IP.
status() {  # status ip nombre
   local linea="$(grep "^$1" "$HOSTS")"
   if [ -n "$linea" ]; then  #IP presente
      echo "$linea" | egrep -qw "$2"'$'
      return $?
   fi
   grep -qw "$2"'$' "$HOSTS"
   return $(($?+2))
}

# Asocia un nombre
# $1: La dirección IP
# $2: El nombre
# $3: add/old
asociarNombre() {
   local level

   status $1 $2
   case $? in
      0)
         log warning "$3: La tupla ($1, $2) ya existe"
         ;;
      1)
         case $3 in
            add) level=warning ;;
            old) level=info ;;
         esac
         log $level "$3: $1 tiene como nuevo nombre $2"
         sed -i '/^'$1'/{s:.*:'$1'\t'$2':;q}' $HOSTS
         ;;
      2)
         log err "$3: nombre $2 estaba asociado a otra IP. Se asocia a $1"
         sed -i '/'$2'$/{s:.*:'$1'\t'$2':;q}' $HOSTS
         ;;
      3)
         case $3 in
            add) level=info ;;
            old) level=warning ;;
         esac
         log $level "$3: $1 se asocia al nombre $2"
         printf "$1\t$2\n"   >> "$HOSTS"
         ;;
   esac
}

revocarNombre() {
   status $1 $2
   case $? in
      0)
         log info "$3: Se borra el nombre $2 asociado a $1"
         sed -i '/^'$1'/d' "$HOSTS"
         ;;
      1)
         log err "$3: $1 tiene asociado un nombre distinto a $2"
         sed -i '/^'$1'/d' "$HOSTS"
         ;;
      2)
         log err "$3: Nombre $2 no asociado a $1"
         ;;
      3)
         log err "$3: $1 no tiene asociado ningún nombre"
         ;;
   esac
}

[ ! -f "$HOSTS" ] && touch "$HOSTS"

if [ "$ACTION" = "del" ]; then
   revocarNombre "$IP" "$(generarNombre)$DOMAIN" $ACTION
else
   asociarNombre "$IP" "$(generarNombre)$DOMAIN" $ACTION
fi

# Hacemos que dnsmasq recargue el fichero $HOSTS
kill -1 $(pgrep dnsmasq)
