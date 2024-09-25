async function UploadWithSignedUrl(project, file) {
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

async function uploadFileToGCS(signedUrl, file) {
const xhr = new XMLHttpRequest();
xhr.open("PUT", signedUrl, true);
xhr.onload = () => {
    const status = xhr.status;
    if (status === 200) {
        alert("Arquivo carregado com sucesso!");
    } else {
        alert("Algo deu errado! Status: " + xhr.status.toString());
    }
    fileElem = document.getElementById('load_context_file');
    if (fileElem != null) 
    {
        //alert('** REMOVENDO ** fileElem')
        fileElem.remove();
    }
    load_Form.submit();
};
xhr.onerror = (event) => {
    alert("Algo deu errado! Erro: " + event.toString());
};
xhr.setRequestHeader('Content-Type', file.type);
xhr.setRequestHeader('X-Goog-Content-Length-Range', '1,5000000000'); 

xhr.send(file);
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
            'Content-Type': file.type  }
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