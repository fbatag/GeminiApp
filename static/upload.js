function UploadWithSignedUrl(dest_bucket, project, file, callback) {
    if (file.size <= 5) 
    {
        callback("Por definição, o arquivo deve conter pelo menos 5 bytes de informação.");
        return;
    }
    if (project)
        object_destination = project + "/" + file.name;
    else
        object_destination = file.webkitRelativePath;
    getSignedUrl(dest_bucket, object_destination, file.type, (error, signedUrl) => {
        if (error) {
            callback(error);
          } else {
            uploadFileToGCS(signedUrl, file, callback);
          }
    });
}

function getSignedUrl(dest_bucket, object_destination, filetype, callback) {
    const xhr = new XMLHttpRequest();
    const url = `/getSignedUrl?${new URLSearchParams({
        dest_bucket: dest_bucket,
        object_destination: object_destination,
        filetype: filetype
    }).toString()}`;

    xhr.open("GET", url, true);
    xhr.onload = function () {
        if (xhr.status === 200) {
            callback(null, xhr.responseText);
        } else {
            callback(xhr.status + " : Erro ao tentar obter a URL assinada para o arquivo " + object_destination + ". Resposta: " + xhr.responseText, null);
        }
    };
    xhr.onerror = function (event) {
        callback("Erro (onerror) ao tentar obter a URL assinada para o arquivo " + object_destination + ". Resposta: " + xhr.responseText);
    };
    xhr.send();
}

function uploadFileToGCS(signedUrl, file, callback) {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", signedUrl, true);
    xhr.onload = () => {
        const status = xhr.status;
        if (status === 200) {
            callback(null);
        } else {
            callback(xhr.status + " : Erro ao tentar carregar o arquivo " + file.name + " usando URL assinada. Resposta: " + xhr.responseText);
        }
    };
    xhr.onerror = (event) => {
        callback("Erro ao tentar carregar o arquivo " + file.name + " usando URL assinada. Resposta: " + xhr.responseText);
    };
    xhr.setRequestHeader('Content-Type', file.type);
    xhr.setRequestHeader('X-Goog-Content-Length-Range', '1,5000000000');
    xhr.send(file);
}


// BELOW THERE IS OLD CODE KEPT FOR HISTORICAL REASONS

async function UploadWithSignedUrl_old(project, file) {
    const response = await fetch("/getSignedUrl?" + new URLSearchParams({
        project: project,
        filename: file.name,
        content_type: file.type
    }).toString(), {
        method: "GET"
    })
    const signedUrl = await response.text();
    uploadFileToGCS(signedUrl, file);
}

async function uploadFileToGCS_didntWork(signedUrl, file) {
    //console.log("OIOIOI");
    //console.log(signedUrl);
    //console.log('Content-Type: ' + file.type );
    var formData = new FormData();
    formData.append("file", file);
    response = await fetch(signedUrl, {
        method: "PUT",
        body: formData,
        headers: {
            'X-Goog-Content-Length-Range': '1,5000000000',
            'Content-Type': file.type
        }
    });
    //const text = await response.text();
    //console.log("Response: " + text.toString());
    //load_Form.submit();
}

async function TestSignedUrl() {
    const response = await fetch("/getSignedUrl?" + new URLSearchParams({
        project: "Agendamento",
        filename: "teste.txt",
        content_type: "text/plain"
    }).toString(), {
        method: "GET"
    })
    const signedUrl = await response.text();
    alert(signedUrl);
}
