/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

const maintenance_url = "/maintenance"

maintenance_redirect = (status) => {
    if (status == 503) {
        window.location.replace(maintenance_url)
    }
}

function apiCall() {
    var self = this;
    self.ajax = function(uri,method, data) {
        //console.log('Ajax to uri '+uri+' with method '+method+' and data: '+data)
//        if(uri.endsWith('/')){uri=uri.substring(0, uri.length - 1);}
                var request = {
                    url: uri,
                    type: method,
                    contentType: "application/json",
                    accepts: "application/json",
                    cache: false,
                    dataType: 'json',
                    data: JSON.stringify(data),
                    error: function(jqXHR) {
                        maintenance_redirect(jqXHR.status)
                    }
                };
                return $.ajax(request);
    };

    self.ajax_async = function(uri,method, data) {
                var request = {
                    url: uri,
                    type: method,
                    contentType: "application/json",
                    accepts: "application/json",
                    async: false,
                    cache: false,
                    dataType: 'json',
                    data: JSON.stringify(data),
                    error: function(jqXHR) {
                        maintenance_redirect(jqXHR.status)
                    }
                };
                return $.ajax(request);
    }
}

var api = new apiCall();

