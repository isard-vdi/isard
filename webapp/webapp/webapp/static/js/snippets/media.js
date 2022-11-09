

    function replaceMedia_arrays(parent_id,data){
        data['create_dict']={'hardware':{'isos':    parseMedia(parent_id,'m-isos'),
                                        'floppies': parseMedia(parent_id,'m-floppies')}}
        delete data['m-isos'];
        delete data['m-floppies'];
        return data
    }

    function parseMedia(parent_id,id){
        d=$(parent_id+" #"+id).select2("val")
        if(d==null){
                return [];
        }
        nd=[]
        d.forEach(function(data)
        {
            nd.push({'id':data})
        });
        return nd
    }

    function setMediaIds(isos){
        nd=[]
        isos.forEach(function(iso)
        {
            nd.push({'id':iso})
        });
        return nd
    }



    function setMedia_add(parentid){
        ids=['m-isos','m-floppies']
         $.each(ids,function(idx,id) {
             $(parentid+" #"+id).select2({
                minimumInputLength: 2,
                multiple: true,
                ajax: {
                    type: "POST",
                    url: '/api/v3/admin/allowed/term/media',
                    dataType: 'json',
                    contentType: "application/json",
                    delay: 250,
                    data: function (params) {
                        return  JSON.stringify({
                            term: params.term,
                            pluck: ['id','name'],
                            kind: id.replace('m-','')
                        });
                    },
                    processResults: function (data) {
                        return {
                            results: $.map(data, function (item, i) {
                                return {
                                    text: item.name,
                                    id: item.id
                                }
                            })
                        };
                    }
                },
            });
        });

    }



