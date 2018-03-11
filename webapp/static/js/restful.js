/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

function apiCall() {
    var self = this;
    self.ajax = function(uri,method, data) {
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
                        console.log("ajax error " + jqXHR.status);
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
                        console.log("ajax error " + jqXHR.status);
                    }
                };
                return $.ajax(request);
    }
}

var api = new apiCall();

