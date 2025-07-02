<?php

// Modified default configuration to add categories from environment variable
// Original: https://raw.githubusercontent.com/kristophjunge/docker-test-saml-idp/refs/heads/master/config/simplesamlphp/authsources.php

$config = array(

    'admin' => array(
        'core:AdminPassword',
    ),

    'example-userpass' => array(
        'exampleauth:UserPass',
        'user1:user1pass' => array(
            'uid' => array('1'),
            'eduPersonAffiliation' => array('group1'),
            'email' => 'user1@example.com',
            'categories' => explode(',', getenv('AUTHENTICATION_TEST_SAML_CATEGORY_IDS')),
        ),
        'user2:user2pass' => array(
            'uid' => array('2'),
            'eduPersonAffiliation' => array('group2'),
            'email' => 'user2@example.com',
            'categories' => explode(',', getenv('AUTHENTICATION_TEST_SAML_CATEGORY_IDS')),
        ),
    ),

);
