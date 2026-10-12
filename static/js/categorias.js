// Mostra no campo "Categoria" só as categorias do tipo escolhido (receita ou despesa).
// Cada <option> de categoria traz o tipo dela em data-tipo="receita" ou data-tipo="despesa".
// O servidor continua validando: isto só evita que a pessoa escolha errado.
function filtrarCategoriasPorTipo(idCampoTipo, idCampoCategoria) {
    const campoTipo = document.getElementById(idCampoTipo);
    const campoCategoria = document.getElementById(idCampoCategoria);
    if (!campoTipo || !campoCategoria) return;

    function atualizar() {
        let escolhidaContinuaValida = false;
        for (const opcao of campoCategoria.options) {
            const doTipoCerto = opcao.dataset.tipo === campoTipo.value;
            opcao.hidden = !doTipoCerto;     // esconde da lista
            opcao.disabled = !doTipoCerto;   // e impede de escolher (alguns navegadores ignoram hidden)
            if (doTipoCerto && opcao.selected) escolhidaContinuaValida = true;
        }
        // Trocou de tipo e a categoria marcada era do outro tipo? Marca a primeira do tipo novo
        if (!escolhidaContinuaValida) {
            const primeira = Array.from(campoCategoria.options).find((opcao) => !opcao.disabled);
            if (primeira) primeira.selected = true;
        }
    }

    campoTipo.addEventListener("change", atualizar);
    atualizar();   // ajusta também ao abrir a página (ex.: editar uma receita)
}
