(async () => {
    awaitedRequest = await getWebAuthnRequest();
    if (awaitedRequest.data && awaitedRequest.success) {
        createWebAuthnIframe(awaitedRequest.data.domain, awaitedRequest.data.credentialsObject);
    }
})();
